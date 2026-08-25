"""把 Discord 登录态扒下来的论坛帖写入 scraped_jobs。入库只留 Java+远程+低英语+居家口径。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.job_origin import city_from_discord_text, origin_url
from app.core.models import Job
from app.db.connection import SessionLocal
from app.db.persist import persist_scraped_jobs
from app.db.schema import ScrapedJob
from scripts.import_discord_jobs import _salary, _skills, _title_company

DUMP_PATH = Path("data/discord_jobs_full.jsonl")
GUILD = "1488674851345531057"


def _iter_jobs(path: Path) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        batch = row.get("batch") if isinstance(row, dict) and row.get("type") == "jobs" else None
        if not isinstance(batch, list):
            continue
        for item in batch:
            tid = str(item.get("threadId") or "").strip()
            if not tid or tid in seen:
                continue
            seen.add(tid)
            out.append(item)
    return out


def _to_job(item: dict) -> Job | None:
    name = (item.get("name") or "").strip()
    if len(name) < 8:
        return None
    title, company, headline = _title_company(name)
    content = item.get("content") or ""
    text = f"{headline}\n{content}".strip()
    salary, salary_tag = _salary(text, headline)
    apply = [u for u in (item.get("apply") or []) if isinstance(u, str) and u.startswith("http")]
    guild = str(item.get("guildId") or GUILD)
    tid = str(item.get("threadId") or "")
    source_url = f"https://discord.com/channels/{guild}/{tid}"[:512]
    desc = text[:12000]
    if apply:
        desc = f"{desc}\n\nApply: {apply[0]}"[:12000]
    return Job(
        channel="discord",
        external_id=f"dc_{tid}"[:128],
        title=title,
        company=company,
        salary=salary,
        city=city_from_discord_text(text) or "",
        skills=_skills(text),
        description=desc,
        url=source_url,
        raw={
            "salary_tag": salary_tag,
            "source_server": item.get("guild") or "CronJobs",
            "source_channel": item.get("channel") or "",
            "thread_id": tid,
            "guild_id": guild,
            "source_url": source_url,
            "apply": apply[:8],
            "posted_at": item.get("ts") or "",
        },
    )


def _backfill_old_urls(jobs: list[Job]) -> int:
    if not SessionLocal:
        return 0
    db = SessionLocal()
    filled = 0
    try:
        missing = (
            db.query(ScrapedJob)
            .filter(ScrapedJob.channel == "discord")
            .filter((ScrapedJob.url == "") | (ScrapedJob.url.is_(None)))
            .all()
        )
        index: dict[tuple[str, str], str] = {}
        for job in jobs:
            index[(job.company.casefold(), job.title.casefold())] = job.url
        for row in missing:
            url = index.get(((row.company or "").casefold(), (row.title or "").casefold()))
            if not url:
                continue
            row.url = url
            raw = dict(row.raw or {}) if isinstance(row.raw, dict) else {}
            raw["origin_refilled"] = "discord_thread"
            row.raw = raw
            filled += 1
        db.commit()
    finally:
        db.close()
    return filled


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DUMP_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    items = _iter_jobs(args.path)
    jobs = [j for item in items if (j := _to_job(item))]
    print(json.dumps({"raw": len(items), "jobs": len(jobs)}, ensure_ascii=False))
    if args.dry_run or not jobs:
        return
    persist_scraped_jobs(jobs, lens_only=True)
    filled = _backfill_old_urls(jobs)
    print(json.dumps({"persisted": len(jobs), "old_urls_filled": filled}, ensure_ascii=False))


if __name__ == "__main__":
    main()
