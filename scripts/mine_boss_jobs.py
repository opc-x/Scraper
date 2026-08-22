"""从已登录的 BOSS 直聘翻页挖岗：Java / 远程 / Agent，再按简历加权筛选。

登录态优先读 Cursor 侧边浏览器 Cookie（wt2 等），不把 __zp_stoken__ 写入配置。
翻页走 DrissionPage 监听 joblist 接口，直连 HTTP 会被 code 37 风控。

用法：
    python -m scripts.mine_boss_jobs
    python -m scripts.mine_boss_jobs --min-jobs 150 --pages 10
    python -m scripts.mine_boss_jobs --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

from app.adapters.boss import BOSS_CITY_MAP, BossAdapter
from app.core.channel_config import save_channel_config
from app.core.models import Job
from app.core.resume import PROJECT_MATCH

CURSOR_COOKIES = Path.home() / "Library/Application Support/Cursor/Partitions/cursor-browser/Cookies"
KEEP_COOKIES = ("wt2", "zp_at", "bst", "ab_guid", "__a", "lastCity")
OUT_JSON = Path("data/boss_jobs.json")
OUT_MD = Path("data/boss_shortlist.md")

JAVA = re.compile(r"\b(java|spring(?:\s*boot)?|jvm)\b", re.I)
AGENT = re.compile(
    r"\b(ai agent|agent engineer|agentic|langchain|langgraph|crewai|autogen|"
    r"multi[- ]agent|mcp|coding agent)\b|智能体",
    re.I,
)
REMOTE = re.compile(r"远程|居家|在家办公|\bremote\b|wfh", re.I)
HANGZHOU = re.compile(r"杭州|hangzhou", re.I)
OVERSEAS = re.compile(r"海外|驻外|海归|新加坡|美国|日本|欧洲|马来|泰国|越南|出国", re.I)
JUNK = re.compile(
    r"校招|应届|实习|兼职|主播|带货|销售|客服|运营|设计师|前端|ios|android|"
    r"产品经理|人事|招聘|财务",
    re.I,
)
SENIOR = re.compile(r"架构|负责人|专家|资深|高级|tech lead|staff|principal|director", re.I)

QUERIES = [
    ("Java", "杭州", "职位"),
    ("Java 远程", "全国", "职位"),
    ("Java 架构师", "杭州", "职位"),
    ("Java 技术专家", "杭州", "职位"),
    ("AI Agent", "杭州", "职位"),
    ("智能体", "杭州", "职位"),
    ("Java", "全国", "海归"),
    ("Java 海归", "全国", "海归"),
    ("Java 留学生", "全国", "海归"),
    ("Java", "全国", "海外"),
    ("Java 驻外", "全国", "海外"),
    ("海外 Java", "全国", "海外"),
]


def load_cursor_cookie() -> str:
    if not CURSOR_COOKIES.exists():
        return ""
    con = sqlite3.connect(f"file:{CURSOR_COOKIES}?mode=ro", uri=True)
    rows = {
        name: value
        for name, value in con.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE '%zhipin%' AND value != ''"
        )
    }
    con.close()
    parts = [f"{k}={rows[k]}" for k in KEEP_COOKIES if rows.get(k)]
    return "; ".join(parts)


def haystack(job: Job) -> str:
    skills = " ".join(job.skills or [])
    return f"{job.title} {job.company} {job.city} {skills} {job.description}"


def buckets(job: Job) -> list[str]:
    text = haystack(job)
    found: list[str] = []
    if JAVA.search(text):
        found.append("java")
    if AGENT.search(text):
        found.append("agent")
    if REMOTE.search(text) or job.city in {"在家办公", "远程"}:
        found.append("remote")
    if HANGZHOU.search(job.city or "") or HANGZHOU.search(text):
        found.append("hangzhou")
    if OVERSEAS.search(text):
        found.append("overseas")
    return found


def resume_score(job: Job) -> int:
    text = haystack(job)
    score = 0
    if JAVA.search(text):
        score += 25
    if AGENT.search(text):
        score += 20
    if REMOTE.search(text) or job.city in {"在家办公", "远程"}:
        score += 20
    elif HANGZHOU.search(job.city or ""):
        score += 12
    if SENIOR.search(text):
        score += 18
    if PROJECT_MATCH.search(text):
        score += 15
    if JUNK.search(job.title or ""):
        score -= 40
    exp = job.experience or ""
    if re.search(r"应届|在校|1年以内", exp):
        score -= 25
    return max(0, min(100, score))


def keep_job(job: Job) -> bool:
    if not job.external_id or JUNK.search(job.title or ""):
        return False
    tags = buckets(job)
    if not ({"java", "agent"} & set(tags)):
        return False
    if not ({"remote", "hangzhou", "overseas"} & set(tags)):
        return False
    return resume_score(job) >= 40


def fetch_httpx(keyword: str, city: str, page_no: int, cookies: dict, page_size: int = 30) -> tuple[list[Job], object]:
    import httpx
    from app.adapters.boss import BossAdapter
    from app.core.models import SearchRequest

    city_code = BOSS_CITY_MAP.get(city, "100010000")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": f"https://www.zhipin.com/web/geek/jobs?query={keyword}&city={city_code}",
        "Accept": "application/json",
    }
    params = {
        "scene": 1,
        "query": keyword,
        "city": city_code,
        "page": page_no,
        "pageSize": page_size,
    }
    with httpx.Client(trust_env=False, timeout=20, headers=headers, cookies=cookies) as client:
        r = client.get("https://www.zhipin.com/wapi/zpgeek/search/joblist.json", params=params)
    data = r.json()
    code = data.get("code")
    if code not in (0, None, "0"):
        print(f"[boss] api code={code} {data.get('message')}", flush=True)
        return [], code
    req = SearchRequest(keyword=keyword, city=city, channel="boss", page=page_no)
    return BossAdapter._jobs_from_payload(data, req), code


def search_page(adapter: BossAdapter, keyword: str, city: str, page: int) -> list[Job]:
    return adapter.fetch_joblist(keyword, city, page)


def cookie_dict() -> dict[str, str]:
    if not CURSOR_COOKIES.exists():
        return {}
    con = sqlite3.connect(f"file:{CURSOR_COOKIES}?mode=ro", uri=True)
    rows = {
        name: value
        for name, value in con.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE '%zhipin%' AND value != ''"
        )
    }
    con.close()
    return rows


def dump(kept: dict[str, Job], seen: dict[str, Job], dry_run: bool) -> list[Job]:
    rows = sorted(kept.values(), key=lambda j: (-int(j.raw.get("resume_score", 0)), j.title))
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps([j.model_dump() for j in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"# BOSS 短名单 {len(rows)} 条",
        "",
        "筛选：Java 或 Agent，且远程/居家或杭州；校招实习销售等剔除；按简历加权排序。",
        "",
        "| 分 | 方向 | 岗位 | 公司 | 城市 | 薪资 |",
        "|---:|---|---|---|---|---|",
    ]
    for job in rows:
        tags = ",".join(job.raw.get("buckets") or [])
        lines.append(
            f"| {job.raw.get('resume_score', 0)} | {tags} | [{job.title}]({job.url}) "
            f"| {job.company} | {job.city} | {job.salary} |"
        )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tag_counts = Counter(tag for job in rows for tag in job.raw.get("buckets") or [])
    print(f"[boss] 抓到 {len(seen)} 条，筛后 {len(rows)} {dict(tag_counts)} -> {OUT_JSON}", file=sys.stderr)
    if not dry_run and rows:
        from app.db.persist import persist_scraped_jobs

        persist_scraped_jobs(rows)
        print(f"[boss] 已写入 scraped_jobs {len(rows)} 条", file=sys.stderr)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-jobs", type=int, default=150)
    ap.add_argument("--pages", type=int, default=10)
    ap.add_argument("--sleep", type=float, default=4.0)
    ap.add_argument("--verify-timeout", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--httpx", action="store_true", help="走侧边浏览器 Cookie 直连接口，不另开 Chrome")
    args = ap.parse_args()

    cookies = cookie_dict()
    if "wt2" not in cookies:
        print("没有 wt2：Cursor 侧边浏览器里的 BOSS 登录态读不到", file=sys.stderr)
        sys.exit(1)
    save_channel_config("boss", {"enabled": True, "cookie": load_cursor_cookie()})

    seen: dict[str, Job] = {}
    kept: dict[str, Job] = {}
    adapter = None
    try:
        if not args.httpx:
            adapter = BossAdapter()
            page = adapter._ensure_page()
            print("[boss] 浏览器已弹出，有验证就点，点完我自动接着翻", flush=True)
            page.get("https://www.zhipin.com/web/geek/jobs?query=Java&city=101210100")
            if not adapter.wait_if_verify(args.verify_timeout):
                sys.exit(2)
        print("[boss] 职位 / 海归 / 海外 开始翻", flush=True)
        for keyword, city, tab in QUERIES:
            city_code = BOSS_CITY_MAP.get(city, city)
            print(f"[boss] [{tab}] {keyword} @ {city}({city_code})", flush=True)
            empty_pages = 0
            blocked = False
            for page_no in range(1, args.pages + 1):
                if args.httpx:
                    jobs, code = fetch_httpx(keyword, city, page_no, cookies)
                    if code in (35, 36, 37, "35", "36", "37"):
                        dump(kept, seen, args.dry_run)
                        print("[boss] 风控了，停。侧边浏览器过验证后再跑", flush=True)
                        blocked = True
                        break
                else:
                    jobs = search_page(adapter, keyword, city, page_no)
                    if adapter.last_code in (35, 36, 37, "35", "36", "37"):
                        dump(kept, seen, args.dry_run)
                        if not adapter.recover_from_block(args.verify_timeout):
                            blocked = True
                            break
                        jobs = search_page(adapter, keyword, city, page_no)
                if not jobs:
                    empty_pages += 1
                    print(f"  page {page_no}: 0", flush=True)
                    adapter.wait_if_verify(args.verify_timeout)
                    if empty_pages >= 2:
                        break
                    time.sleep(args.sleep)
                    continue
                empty_pages = 0
                new = 0
                for job in jobs:
                    if job.external_id in seen:
                        continue
                    seen[job.external_id] = job
                    job.raw = dict(job.raw or {})
                    job.raw["buckets"] = buckets(job)
                    job.raw["resume_score"] = resume_score(job)
                    job.raw["query"] = keyword
                    job.raw["tab"] = tab
                    if keep_job(job):
                        kept[job.external_id] = job
                        new += 1
                print(
                    f"  page {page_no}: got {len(jobs)} unique {len(seen)} kept {len(kept)} +{new}",
                    flush=True,
                )
                dump(kept, seen, args.dry_run)
                if len(kept) >= args.min_jobs and page_no >= 3:
                    break
                time.sleep(args.sleep)
            if blocked or len(kept) >= args.min_jobs:
                break
    finally:
        dump(kept, seen, args.dry_run)
        if adapter is not None:
            import asyncio

            asyncio.run(adapter.close())


if __name__ == "__main__":
    main()
