"""给挖到的 X 账号打标签 —— 走 app.infra.local_ai（codex 优先，claude 兜底）。

按 CLAUDE.md 的架构：打标签这步在本机 AI 环境跑，生产服务只读库展示。
标签维度：薪资 / 是否远程 / 地域 / 技术栈 / 岗位方向 / 团队文化 / 资历要求。

用法：
    python -m scripts.tag_x_accounts --limit 50          # 只打没打过的
    python -m scripts.tag_x_accounts --retag             # 全部重打
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.infra.local_ai import LocalAiError, run_sync

RAW_PATH = Path("data/x_mining_raw.json")
OUT_PATH = Path("data/x_tagged_accounts.json")

PROMPT = """你在评估一个 X (Twitter) 账号，判断它对一个"找海外远程工作的中国程序员"有多大价值。

账号：@{handle}（{name}）
简介：{bio}
粉丝数：{followers}
最近发帖（最多 20 条）：
{posts}

只输出一个 JSON 对象，不要任何其他文字、不要 markdown 代码块：

{{
  "is_hiring_account": true/false,       // 是否主要发布招聘信息（不是偶尔转发一两条）
  "confidence": 0-100,                    // "这是个招聘账号"的把握
  "value_score": 0-100,                   // 对上述求职者的实际价值（岗位可投递性）
  "roles": [],                            // 命中的方向，从 ["nodejs","java","python","agent","frontend","devops","data","other"] 里选
  "salary": "",                           // 帖子里出现的薪资范围，原文照抄；没有填 ""
  "remote": "",                           // "fully_remote" | "hybrid" | "onsite" | "unknown"
  "regions": [],                          // 岗位地域限制，如 ["US","EU","worldwide"]；无限制填 ["worldwide"]
  "china_friendly": true/false,           // 中国境内远程能否投递（无地域/时区硬限制、不要求 work authorization）
  "stack": [],                            // 帖子里出现的技术栈关键词
  "culture": "",                          // 团队文化氛围，一句话；看不出填 ""
  "seniority": [],                        // 资历要求，如 ["junior","mid","senior","staff"]
  "spam": true/false,                     // 是否是卖课/卖简历模板/刷单一类垃圾号
  "rationale": ""                         // 一句话说明为什么给这个分
}}"""


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="本轮最多打多少个，0=不限")
    ap.add_argument("--retag", action="store_true")
    ap.add_argument("--min-confidence", type=int, default=60, help="低于此值 kept=false")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    raw = load(RAW_PATH, {})
    tagged: dict = {} if args.retag else load(OUT_PATH, {})

    todo = [h for h, d in raw.items() if d.get("tweets") and h not in tagged]
    if args.limit:
        todo = todo[: args.limit]
    print(f"[tag] 待打标签 {len(todo)} 个（已打 {len(tagged)}）", file=sys.stderr)

    for i, h in enumerate(todo, 1):
        d = raw[h]
        posts = "\n".join(f"- {t[:280]}" for t in (d.get("tweets") or [])[:20])
        try:
            res = run_sync(PROMPT.format(
                handle=h, name=d.get("name") or "", bio=(d.get("bio") or "")[:400],
                followers=d.get("followers"), posts=posts,
            ))
        except LocalAiError as exc:
            print(f"  [{i}/{len(todo)}] @{h} {exc}", file=sys.stderr)
            continue
        res["handle"] = h
        res["profile_url"] = f"https://x.com/{h}"
        res["bio"] = d.get("bio") or ""
        res["followers"] = d.get("followers")
        tagged[h] = res
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(tagged, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"  [{i}/{len(todo)}] @{h} conf={res.get('confidence')} "
            f"value={res.get('value_score')} roles={res.get('roles')}",
            file=sys.stderr,
        )
        time.sleep(1)

    if args.no_db:
        return

    rows = []
    for h, r in tagged.items():
        if r.get("spam"):
            continue
        rows.append({
            "handle": h,
            "profile_url": r.get("profile_url", ""),
            "bio": r.get("bio", "")[:2000],
            "confidence": int(r.get("confidence") or 0),
            "value_score": int(r.get("value_score") or 0),
            "kept": int(r.get("confidence") or 0) >= args.min_confidence,
            "tags": {
                "roles": r.get("roles") or [],
                "salary": r.get("salary") or "",
                "remote": r.get("remote") or "unknown",
                "regions": r.get("regions") or [],
                "china_friendly": bool(r.get("china_friendly")),
                "stack": r.get("stack") or [],
                "culture": r.get("culture") or "",
                "seniority": r.get("seniority") or [],
            },
            "rationale": r.get("rationale") or "",
        })
    try:
        from app.db.persist import persist_mined_accounts
        persist_mined_accounts("x", "remote_hiring", rows)
        print(f"[tag] 写库 {len(rows)} 条", file=sys.stderr)
    except Exception as e:  # noqa: BLE001
        print(f"[tag] 写库失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
