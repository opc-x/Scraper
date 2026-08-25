"""Telegram 远程招聘公开频道发现。

不需要登录态：公开频道的网页预览 https://t.me/s/<name> 直接可读，
拿到订阅数 + 最近 20 条帖子。用种子频道滚雪球（抓帖子里的 @mention 和
t.me 链接）扩散发现新频道，再按招聘关键词打分过滤。

用法：
    python -m scripts.mine_telegram_job_channels --limit 100 --hops 2
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"}

SEEDS = [
    "Cvflow",
    "Freelancer",
    "Python",
    "React_Native_Status",
    "Relocats",
    "RemoteJSbot",
    "TechGuide",
    "ai_ml_jobs",
    "angularDevelopers",
    "codenjobs",
    "cryptojobswork",
    "devjobs",
    "devopsjobs",
    "digitalbroccoli",
    "europeanremotejobs",
    "fedevelopment",
    "findmyremote_frontend",
    "flutterDart",
    "freelancersit",
    "freshopenings",
    "front_end_first",
    "getremotejobs",
    "golang_jobs",
    "itfreelancers",
    "javascriptgroup",
    "jobs_abroad",
    "llm_jobs",
    "nodejs_jobs",
    "qa_jobs_remote",
    "reactjobs",
    "remote_ai_jobs",
    "remote_devops_jobs",
    "remote_frontend_jobs",
    "remote_it_jobs",
    "remote_job_offers_en",
    "remote_jobs_tech",
    "remote_python_jobs",
    "remotebackendjobs",
    "remoteforce",
    "remoteit",
    "remotejobs",
    "remotejobshg",
    "remotejobss",
    "remotelist",
    "remoteok",
    "remoters",
    "remotework",
    "rustjobs",
    "startup_jobs_remote",
    "thedevs",
    "uajobit",
    "web3_jobs",
    "webdel",
    "weworkremotely",
    "yc_jobs",
]

TITLE_RE = re.compile(
    r'<div class="tgme_channel_info_header_title"[^>]*><span[^>]*>(.*?)</span>', re.S
)
DESC_RE = re.compile(r'<div class="tgme_channel_info_description"[^>]*>(.*?)</div>', re.S)
SUBS_RE = re.compile(
    r'<span class="counter_value">([\d.,KMk]+)</span>\s*<span class="counter_type">subscribers'
)
MSG_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
LINK_RE = re.compile(r"(?:https?://)?t\.me/(?:s/)?([A-Za-z][A-Za-z0-9_]{4,31})")
AT_RE = re.compile(r"@([A-Za-z][A-Za-z0-9_]{4,31})")

JOB_KW = [
    "hiring",
    "remote",
    "job",
    "vacancy",
    "position",
    "salary",
    "apply",
    "developer",
    "engineer",
    "full-time",
    "contract",
    "freelance",
    "we're looking",
    "招聘",
    "远程",
    "岗位",
]
NOISE = ["porn", "casino", "bet", "nude", "18+", "crypto pump", "signal"]


def strip_tags(t: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"\s+", " ", t)).strip()


def to_int(s: str) -> int:
    s = s.replace(",", "").strip()
    mult = {"K": 1000, "k": 1000, "M": 1_000_000}
    if s and s[-1] in mult:
        return int(float(s[:-1]) * mult[s[-1]])
    return int(float(s or 0))


def fetch_channel(name: str) -> dict | None:
    try:
        req = urllib.request.Request(f"https://t.me/s/{name}", headers=UA)
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.geturl().rstrip("/").split("/")[-1].lower() != name.lower():
                return None  # 302 到非频道页 = 不是公开频道
            body = r.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None

    msgs = [strip_tags(m) for m in MSG_RE.findall(body)]
    msgs = [m for m in msgs if len(m) > 20]
    if not msgs:
        return None
    blob = " ".join(msgs).lower()
    subs_m = SUBS_RE.search(body)
    title_m = TITLE_RE.search(body)
    desc_m = DESC_RE.search(body)

    hits = [k for k in JOB_KW if k in blob]
    return {
        "channel": "telegram",
        "username": name,
        "url": f"https://t.me/{name}",
        "preview_url": f"https://t.me/s/{name}",
        "title": strip_tags(title_m.group(1)) if title_m else name,
        "description": (strip_tags(desc_m.group(1)) if desc_m else "")[:300],
        "subscribers": to_int(subs_m.group(1)) if subs_m else 0,
        "recent_msgs": len(msgs),
        "job_keyword_hits": hits,
        "job_score": len(hits),
        "is_noise": any(n in blob for n in NOISE),
        "sample_post": msgs[-1][:400] if msgs else "",
        "_links": set(LINK_RE.findall(body[body.find("tgme_widget_message_text") :]))
        | set(AT_RE.findall(blob)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--hops", type=int, default=2)
    ap.add_argument("--min-score", type=int, default=3)
    ap.add_argument("--min-subs", type=int, default=300)
    ap.add_argument("--out", default="data/telegram_job_channels.json")
    args = ap.parse_args()

    seen: set[str] = set()
    kept: list[dict] = []
    _sigs: set = set()
    frontier: list[str] = list(SEEDS)

    # t.me 单次请求 ~8s，必须并发，否则跑一晚上也扫不完
    for hop in range(args.hops + 1):
        batch = [n for n in frontier if n.lower() not in seen][:400]
        if not batch or len(kept) >= args.limit:
            break
        seen.update(n.lower() for n in batch)
        print(f"[hop {hop}] 探测 {len(batch)} 个候选…", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=16) as pool:
            infos = list(pool.map(fetch_channel, batch))

        nxt: set[str] = set()
        for info in infos:
            if not info:
                continue
            nxt |= {x for x in info.pop("_links") if x.lower() not in seen}
            sig = (info["title"], info["subscribers"])
            if (
                not info["is_noise"]
                and info["job_score"] >= args.min_score
                and info["subscribers"] >= args.min_subs
                and sig not in _sigs
            ):
                _sigs.add(sig)
                kept.append(info)
                summary = (
                    f"  ✓ [{len(kept):>3}] @{info['username']} "
                    f"({info['subscribers']:,}) score={info['job_score']}"
                )
                print(
                    summary,
                    file=sys.stderr,
                )
        frontier = sorted(nxt)

    kept.sort(key=lambda r: (r["job_score"], r["subscribers"]), reverse=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[telegram] {len(kept)} 个频道（探测 {len(seen)} 个）-> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
