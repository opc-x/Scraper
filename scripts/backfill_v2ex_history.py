"""V2EX「酷工作」历史回填 —— Atom feed 只有最新 20 条，历史得走节点分页 HTML。

feed 拿到的是当天的，节点页 https://www.v2ex.com/go/jobs?p=N 能往前翻，
每页 21 帖。抓到帖子 URL 后逐个取正文，复用 adapters/v2ex.py 的技术岗过滤。

用法：
    python -m scripts.backfill_v2ex_history --pages 25
"""

from __future__ import annotations

import argparse
import html
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.adapters.v2ex import NON_TECH_RE, TECH_RE
from app.core.models import Job

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"}
NODE_URL = "https://www.v2ex.com/go/jobs?p={p}"
TOPIC_URL = "https://www.v2ex.com/t/{tid}"

TOPIC_ID_RE = re.compile(r'href="/t/(\d+)')
TITLE_RE = re.compile(r'<h1>(.*?)</h1>', re.S)
CONTENT_RE = re.compile(r'<div class="topic_content">(.*?)</div>\s*</div>', re.S)
TIME_RE = re.compile(r'<span class="ago"[^>]*title="([^"]+)"')
SALARY_RE = re.compile(r"(\d+\s*[kK]\s*[-~到]\s*\d+\s*[kK]|\d{4,6}\s*[-~]\s*\d{4,6}|\$\d[\d,]*)")
CITY_RE = re.compile(
    r"(远程|remote|北京|上海|深圳|广州|杭州|成都|武汉|南京|西安|新加坡|东京)", re.I
)
STACK = ["Java", "Python", "Go", "Golang", "Rust", "Node", "TypeScript", "React", "Vue",
         "Spring", "MySQL", "Redis", "Kafka", "Flink", "Spark", "Hadoop", "K8s",
         "Kubernetes", "Docker", "AWS", "LLM", "AI"]


def strip(t: str) -> str:
    t = re.sub(r"<br\s*/?>|</p>", "\n", t or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return html.unescape(re.sub(r"[ \t]+", " ", t)).strip()


def get(url: str) -> str | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
            return r.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


def fetch_topic(tid: str) -> Job | None:
    body = get(TOPIC_URL.format(tid=tid))
    if not body:
        return None
    tm = TITLE_RE.search(body)
    if not tm:
        return None
    title = strip(tm.group(1))
    if not TECH_RE.search(title) or NON_TECH_RE.search(title):
        return None
    cm = CONTENT_RE.search(body)
    content = strip(cm.group(1)) if cm else ""
    posted = ""
    tt = TIME_RE.search(body)
    if tt:
        posted = tt.group(1)
    sal = SALARY_RE.search(f"{title} {content[:1500]}")
    city = CITY_RE.search(f"{title} {content[:600]}")
    blob = f"{title} {content}"
    return Job(
        channel="v2ex",
        external_id=tid,
        title=title[:250],
        company="未知",
        salary=(sal.group(0).strip() if sal else "")[:64],
        city=(city.group(0) if city else "")[:64],
        skills=[s for s in STACK if re.search(rf"\b{re.escape(s)}\b", blob, re.I)][:12],
        description=content[:4000],
        url=TOPIC_URL.format(tid=tid),
        raw={"source": "v2ex", "topic_id": tid, "posted_at_raw": posted},
    )


def parse_posted(raw: str) -> datetime | None:
    # V2EX 的 title 属性形如 "2026-08-15 10:22:31 +08:00"
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", raw or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=25)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    tids: list[str] = []
    for p in range(1, args.pages + 1):
        body = get(NODE_URL.format(p=p))
        if not body:
            break
        found = [t for t in dict.fromkeys(TOPIC_ID_RE.findall(body)) if t not in tids]
        if not found:
            break
        tids.extend(found)
        print(f"  第 {p} 页 +{len(found)}，累计 {len(tids)}", flush=True)
        time.sleep(0.4)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = [j for j in pool.map(fetch_topic, tids) if j]
    print(f"[v2ex] {len(tids)} 个帖子，技术岗 {len(jobs)} 条", flush=True)

    if args.no_db or not jobs:
        return
    from sqlalchemy import text

    from app.db.connection import engine
    from app.db.persist import persist_scraped_jobs
    for i in range(0, len(jobs), 100):
        persist_scraped_jobs(jobs[i:i + 100])
        print(f"  已写 {min(i + 100, len(jobs))}/{len(jobs)}", flush=True)

    dates = {j.external_id: parse_posted(j.raw.get("posted_at_raw", "")) for j in jobs}
    dates = {k: v for k, v in dates.items() if v}
    with engine.connect() as c:
        idmap = dict(c.execute(text(
            "SELECT external_id, id FROM scraped_jobs WHERE channel='v2ex'")).fetchall())
    pairs = [(idmap[k], v) for k, v in dates.items() if k in idmap]
    if pairs:
        cases = " ".join(f"WHEN {i} THEN '{d:%Y-%m-%d %H:%M:%S}'" for i, d in pairs)
        ids = ",".join(str(i) for i, _ in pairs)
        with engine.begin() as c:
            c.execute(text(
                f"UPDATE scraped_jobs SET posted_at = CASE id {cases} END WHERE id IN ({ids})"))
        print(f"[v2ex] 补时间 {len(pairs)} 条", flush=True)
    print("完成", flush=True)


if __name__ == "__main__":
    main()
