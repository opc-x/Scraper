"""X 远程招聘账号批量挖掘 —— 目标 100 个，规则见 rules/x_remote_hiring_accounts.md。

在 mine_x_remote_hiring.py 的基础上做三件事：
1. 查询词扩到几十条（岗位方向 × 招聘话术），把候选池撑起来
2. 抓每个候选的历史发帖 + profile，按关键词占比做机械初筛（置信度那步仍交给 AI）
3. 边跑边落盘，中途挂了下次 --resume 接着跑，不用从头再来一遍请求

用法：
    CHROME_PROFILE_ROOT=~/.scraper/chrome_profiles \
      python -m scripts.mine_x_remote_hiring_bulk --target 100 --resume
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path

from app.channels.x import XAdapter

RAW_PATH = Path("data/x_mining_raw.json")
OUT_PATH = Path("data/x_hiring_accounts.json")

SEARCH_QUERIES = [
    # 通用招聘话术
    "remote job hiring",
    "hiring remote developer",
    "we're hiring remote",
    "remote job alert",
    "remote position open",
    "hiring remote engineer",
    "now hiring remote",
    "remote opportunity apply",
    "join our remote team",
    "fully remote role",
    "remote first hiring",
    "work from anywhere job",
    # 按岗位方向
    "hiring remote backend engineer",
    "hiring remote frontend engineer",
    "hiring remote full stack",
    "hiring remote python developer",
    "hiring remote golang engineer",
    "hiring remote rust engineer",
    "hiring remote devops engineer",
    "hiring remote data engineer",
    "hiring remote machine learning engineer",
    "hiring remote AI engineer",
    "hiring remote LLM engineer",
    "hiring remote AI agent engineer",
    "hiring remote react developer",
    "hiring remote node developer",
    "hiring remote mobile engineer",
    "hiring remote QA engineer",
    "hiring remote SRE",
    "hiring remote platform engineer",
    # 招聘方自称
    "remote jobs daily",
    "remote jobs board",
    "remote hiring feed",
    "we are hiring engineers remote",
    "startup hiring remote engineer",
]

HIRING_KW = [
    "hiring",
    "we're hiring",
    "we are hiring",
    "job",
    "jobs",
    "role",
    "position",
    "vacancy",
    "apply",
    "career",
    "opening",
    "opportunity",
    "recruit",
    "salary",
    "remote",
    "full-time",
    "contract",
    "onsite",
    "relocation",
    "visa",
]
SPAM_KW = [
    "resume template",
    "course",
    "bootcamp enroll",
    "dm me to earn",
    "crypto signal",
    "forex",
    "giveaway",
    "follow back",
    "click here to win",
    "investment plan",
]
BIO_HIRING = re.compile(
    r"\b(hiring|jobs?|recruit\w*|talent|headhunt\w*|career|HR|staffing|remote work)\b", re.I
)


def score(tweets: list[str], bio: str) -> dict:
    """机械初筛：算招聘话术占比 + 垃圾词命中，不做置信度判断（那步给 AI）。"""
    if not tweets:
        return {"hiring_ratio": 0.0, "spam_hits": [], "bio_signal": False, "prescreen": 0}
    hiring_posts = sum(1 for t in tweets if sum(1 for k in HIRING_KW if k in t.lower()) >= 2)
    ratio = hiring_posts / len(tweets)
    spam = [k for k in SPAM_KW if any(k in t.lower() for t in tweets)]
    bio_sig = bool(BIO_HIRING.search(bio or ""))
    pre = int(ratio * 80) + (20 if bio_sig else 0) - 30 * len(spam)
    return {
        "hiring_ratio": round(ratio, 2),
        "spam_hits": spam,
        "bio_signal": bio_sig,
        "prescreen": max(0, min(100, pre)),
    }


def load_raw(path: Path = RAW_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_raw(raw: dict, path: Path = RAW_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=100, help="要凑够多少个账号")
    ap.add_argument("--resume", action="store_true", help="复用 data/x_mining_raw.json 已抓到的")
    ap.add_argument("--min-prescreen", type=int, default=25)
    ap.add_argument("--pace", type=float, default=2.5, help="每次请求后的基础间隔秒数")
    ap.add_argument("--batch-size", type=int, default=0, help="本次最多抓几个主页，0 为不限")
    ap.add_argument("--skip-discovery", action="store_true", help="只续抓已有候选，不再搜索")
    ap.add_argument("--raw-path", type=Path, default=RAW_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    raw = load_raw(args.raw_path) if args.resume else {}
    print(f"已有 {len(raw)} 个账号的原始数据", file=sys.stderr)

    a = XAdapter()
    candidates: dict[str, int] = {sn: v.get("hits", 1) for sn, v in raw.items()}

    try:
        print("=== 阶段 1：搜索发现候选账号 ===", file=sys.stderr)
        queries = [] if args.skip_discovery else SEARCH_QUERIES
        for q in queries:
            # 候选池要留足余量，初筛会刷掉一大半
            if args.target and len(candidates) >= args.target * 5:
                break
            try:
                posts = a._search_posts_sync(q)
            except Exception as e:  # noqa: BLE001
                print(f"  搜索 '{q}' 失败: {e}", file=sys.stderr)
                a.reset_page()
                continue
            for p in posts:
                sn = p.get("screen_name")
                if sn:
                    candidates[sn] = candidates.get(sn, 0) + 1
                    raw.setdefault(sn, {"hits": 0, "tweets": [], "bio": ""})
                    raw[sn]["hits"] = candidates[sn]
            save_raw(raw, args.raw_path)
            print(f"  '{q}' -> {len(posts)} 帖，候选池 {len(candidates)}", file=sys.stderr)
            time.sleep(args.pace + random.random())

        # 旧脚本会把空结果写入 raw；空记录不是成功，--resume 必须重试。
        todo = [
            sn
            for sn in candidates
            if (
                sn not in raw
                or not (raw[sn].get("tweets") or raw[sn].get("bio"))
                and raw[sn].get("attempts", 0) < 3
            )
        ]
        todo.sort(key=lambda sn: candidates.get(sn, 0), reverse=True)
        if args.batch_size:
            todo = todo[: args.batch_size]
        print(f"\n=== 阶段 2：抓历史发帖 + profile（待抓 {len(todo)}）===", file=sys.stderr)
        for i, sn in enumerate(todo, 1):
            try:
                tweets, profile = a.fetch_user_bundle_sync(sn)
                profile = profile or {}
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(todo)}] @{sn} 失败: {e}", file=sys.stderr)
                raw.setdefault(sn, {"hits": candidates.get(sn, 1), "tweets": [], "bio": ""})
                raw[sn]["attempts"] = raw[sn].get("attempts", 0) + 1
                save_raw(raw, args.raw_path)
                a.reset_page()
                continue
            texts = [t["text"] for t in tweets if t.get("text")][:20]
            raw[sn] = {
                "hits": candidates.get(sn, 1),
                "tweets": texts,
                "bio": profile.get("profile_bio", {}).get("description", ""),
                "followers": profile.get("relationship_counts", {}).get("followers"),
                "name": profile.get("core", {}).get("name"),
                "attempts": raw.get(sn, {}).get("attempts", 0) + 1,
            }
            if i % 5 == 0:
                save_raw(raw, args.raw_path)  # 边跑边落盘，中断了 --resume 能接上
            print(f"  [{i}/{len(todo)}] @{sn}: {len(texts)} 帖", file=sys.stderr)
            time.sleep(args.pace + random.random())
    finally:
        save_raw(raw, args.raw_path)
        try:
            asyncio.run(a.close())
        except Exception:  # noqa: BLE001
            pass

    rows = []
    for sn, d in raw.items():
        s = score(d.get("tweets") or [], d.get("bio") or "")
        if s["prescreen"] < args.min_prescreen:
            continue
        rows.append(
            {
                "channel": "x",
                "topic": "remote_hiring",
                "handle": sn,
                "name": d.get("name"),
                "profile_url": f"https://x.com/{sn}",
                "bio": (d.get("bio") or "")[:300],
                "followers": d.get("followers"),
                "tweets_total": d.get("tweets_total"),
                "location": d.get("location"),
                "search_hits": d.get("hits"),
                "sample_posts": (d.get("tweets") or [])[:3],
                **s,
            }
        )
    rows.sort(key=lambda r: (r["prescreen"], r["search_hits"]), reverse=True)
    if args.target:  # target=0 表示不设上限，不能切
        rows = rows[: args.target]
    args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[x] 初筛留下 {len(rows)} / 原始 {len(raw)} -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
