"""拉 RemoteOK + WeWorkRemotely 的公开数据源，写入 scraped_jobs。

这俩渠道跟 telegram/x 不一样：字段本来就是结构化的，不需要 LLM 抽取，
所以可以随便定时重跑，成本只有几次 HTTP 请求。

用法：
    python -m scripts.mine_job_boards
    python -m scripts.mine_job_boards --no-db      # 只落 JSON 看看
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from app.adapters.jobboards import JobBoardAdapter
from app.core import salary as salary_lib

OUT = Path("data/job_boards.json")


async def run(args) -> None:
    adapter = JobBoardAdapter()
    try:
        jobs = await adapter.fetch_all()
    finally:
        await adapter.close()

    # 同一个岗位可能同时挂在两家站上，按 (公司, 岗位) 去重，保留带薪资的那条
    best: dict[tuple, object] = {}
    for j in jobs:
        key = (j.company.strip().lower(), j.title.strip().lower())
        old = best.get(key)
        if old is None or (j.salary and not old.salary):
            best[key] = j
    rows = list(best.values())

    for j in rows:
        lo, hi = salary_lib.parse(j.salary)
        j.raw["salary_min_usd"] = lo
        j.raw["salary_max_usd"] = hi

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps([j.model_dump() for j in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    by_ch = Counter(j.channel for j in rows)
    print(f"[boards] 抓到 {len(jobs)} 条，去重后 {len(rows)} 条 {dict(by_ch)}", file=sys.stderr)
    print(f"[boards] 带薪资 {sum(1 for j in rows if j.salary)} 条 -> {OUT}", file=sys.stderr)

    if args.no_db:
        return
    from app.db.persist import persist_scraped_jobs
    for i in range(0, len(rows), 200):
        persist_scraped_jobs(rows[i:i + 200])
        print(f"  已写 {min(i + 200, len(rows))}/{len(rows)}", file=sys.stderr)
    print("[boards] 已写入 scraped_jobs", file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-db", action="store_true")
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
