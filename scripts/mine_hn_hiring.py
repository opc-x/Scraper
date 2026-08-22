"""HN "Who is hiring" 远程岗位挖掘。

走 Algolia 官方公开 API，无需登录态、无反爬。
每条顶层评论 = 一个招聘岗位，抽取公司 / 岗位 / 地点 / 技术栈 / 联系方式。

用法：
    python -m scripts.mine_hn_hiring --months 6 --limit 100 --remote-only
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ALGOLIA = "https://hn.algolia.com/api/v1"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

REMOTE_RE = re.compile(r"\bremote\b", re.I)
ONSITE_ONLY_RE = re.compile(r"\b(onsite only|on-site only|no remote|remote:\s*no)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
URL_RE = re.compile(r"https?://[^\s<>\"]+")
VISA_RE = re.compile(r"visa[:\s]*(yes|no)", re.I)

STACK = [
    "python",
    "typescript",
    "javascript",
    "golang",
    " go ",
    "rust",
    "java",
    "kotlin",
    "swift",
    "ruby",
    "rails",
    "react",
    "vue",
    "node",
    "django",
    "fastapi",
    "kubernetes",
    "aws",
    "gcp",
    "postgres",
    "llm",
    "ai agent",
    "agent",
    "rag",
    "pytorch",
    "c++",
    "elixir",
]


def fetch(url: str, retries: int = 3) -> dict:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            print(f"  retry {i + 1} ({e})", file=sys.stderr)
            time.sleep(2 * (i + 1))
    return {}


def hiring_threads(months: int) -> list[dict]:
    url = f"{ALGOLIA}/search_by_date?tags=story,author_whoishiring&hitsPerPage=60"
    hits = fetch(url).get("hits", [])
    out = [h for h in hits if "who is hiring" in (h.get("title") or "").lower()]
    return out[:months]


def clean(text: str) -> str:
    text = re.sub(r"<p>", "\n", text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_post(node: dict, thread: dict) -> dict | None:
    body = clean(node.get("text") or "")
    if len(body) < 40:
        return None
    head = body.split("\n")[0].strip()
    # 标题行惯例： "Company | Role | Location | Stack"
    parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", head) if p.strip()]
    company = parts[0][:120] if parts else ""
    role = parts[1][:160] if len(parts) > 1 else ""
    stack = sorted({s.strip() for s in STACK if s in body.lower()})
    visa = VISA_RE.search(body)
    urls = [u.rstrip(".,)") for u in URL_RE.findall(body)]
    return {
        "channel": "hackernews",
        "source_thread": thread["title"],
        "thread_id": thread["objectID"],
        "post_id": str(node.get("id")),
        "url": f"https://news.ycombinator.com/item?id={node.get('id')}",
        "posted_by": node.get("author"),
        "posted_at": node.get("created_at"),
        "company": company,
        "role": role,
        "headline": head[:300],
        "is_remote": bool(REMOTE_RE.search(body)) and not ONSITE_ONLY_RE.search(body),
        "visa_sponsor": (visa.group(1).lower() if visa else None),
        "stack": stack,
        "emails": sorted(set(EMAIL_RE.findall(body)))[:3],
        "links": urls[:3],
        "body": body[:2000],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6, help="回溯几期 who-is-hiring")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--remote-only", action="store_true")
    ap.add_argument("--out", default="data/hn_hiring.json")
    args = ap.parse_args()

    rows: list[dict] = []
    for t in hiring_threads(args.months):
        print(f"[hn] {t['title']} ({t.get('num_comments')} comments)", file=sys.stderr)
        item = fetch(f"{ALGOLIA}/items/{t['objectID']}")
        for child in item.get("children") or []:
            row = parse_post(child, t)
            if not row:
                continue
            if args.remote_only and not row["is_remote"]:
                continue
            rows.append(row)
        time.sleep(1)

    rows.sort(key=lambda r: r["posted_at"], reverse=True)
    if args.limit:  # 0 = 不设上限
        rows = rows[: args.limit]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[hn] {len(rows)} 条 -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
