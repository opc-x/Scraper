"""抓取电鸭近 90 天技术职位并幂等写入 scraped_jobs。"""

from __future__ import annotations

import argparse
import asyncio

from app.adapters.eleduck import DEFAULT_MAX_AGE_DAYS, DEFAULT_MIN_JOBS, EleduckAdapter


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument("--min-jobs", type=int, default=DEFAULT_MIN_JOBS)
    parser.add_argument("--fetch-details", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    adapter = EleduckAdapter()
    try:
        jobs = await adapter.fetch_recent(
            max_age_days=args.days,
            min_jobs=args.min_jobs,
            fetch_details=args.fetch_details,
        )
        if not args.dry_run:
            from app.db.persist import persist_scraped_jobs

            persist_scraped_jobs(jobs)
        print(f"eleduck jobs={len(jobs)} days={args.days} persisted={not args.dry_run}")
    finally:
        await adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
