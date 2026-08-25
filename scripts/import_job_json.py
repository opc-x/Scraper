"""把 data/*.json 里的岗位导进 scraped_jobs，带 posted_at。

各挖掘脚本产出的 JSON 字段名不完全一致，这里统一映射一次，
避免每加一个渠道就复制一遍写库逻辑。

用法：
    python -m scripts.import_job_json data/hn_hiring.json --channel hackernews
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.core.models import Job
from app.db.connection import engine
from app.db.persist import persist_scraped_jobs

STACK_HINT = ["java", "spring", "kafka", "spark", "flink", "hadoop", "hive", "python",
              "golang", "node", "rust", "kubernetes", "aws", "postgres", "redis", "llm"]


def parse_dt(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(
            timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def to_job(row: dict, channel: str) -> tuple[Job, datetime | None]:
    raw = dict(row.get("raw") or {})
    posted = parse_dt(row.get("posted_at") or raw.get("posted_at") or raw.get("date"))
    if posted:
        raw["posted_at"] = posted.isoformat()
    body = row.get("body") or row.get("description") or ""
    skills = row.get("skills") or row.get("stack") or [
        s for s in STACK_HINT if s in body.lower()
    ]
    ext = str(row.get("external_id") or row.get("post_id") or row.get("thread_id") or "")
    return Job(
        channel=channel,
        external_id=ext[:128],
        title=(row.get("title") or row.get("role") or row.get("headline") or "未命名")[:250],
        company=(row.get("company") or "未知")[:250],
        salary=(row.get("salary") or "")[:64],
        city=(row.get("city") or ("Remote" if row.get("is_remote") else ""))[:64],
        skills=[str(s)[:40] for s in skills][:12],
        description=body[:4000],
        url=(row.get("url") or "")[:512],
        raw=raw,
    ), posted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--channel", required=True)
    args = ap.parse_args()

    rows = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if isinstance(rows, dict):
        rows = list(rows.values())

    jobs, dates = [], {}
    for r in rows:
        j, dt = to_job(r, args.channel)
        if not j.external_id:
            continue
        jobs.append(j)
        if dt:
            dates[j.external_id] = dt
    print(f"待导入 {len(jobs)} 条（带时间 {len(dates)}）", flush=True)

    for i in range(0, len(jobs), 200):
        persist_scraped_jobs(jobs[i:i + 200], lens_only=True)
        print(f"  已写 {min(i + 200, len(jobs))}/{len(jobs)}", flush=True)

    # posted_at 不在 Job 模型里，写完再批量补
    with engine.connect() as c:
        idmap = dict(c.execute(text(
            "SELECT external_id, id FROM scraped_jobs WHERE channel = :ch"
        ), {"ch": args.channel}).fetchall())
    pairs = [(idmap[k], v) for k, v in dates.items() if k in idmap]
    for i in range(0, len(pairs), 400):
        chunk = pairs[i:i + 400]
        cases = " ".join(f"WHEN {jid} THEN '{dt:%Y-%m-%d %H:%M:%S}'" for jid, dt in chunk)
        ids = ",".join(str(jid) for jid, _ in chunk)
        with engine.begin() as c:
            c.execute(text(
                f"UPDATE scraped_jobs SET posted_at = CASE id {cases} END WHERE id IN ({ids})"))
        print(f"  已补时间 {min(i + 400, len(pairs))}/{len(pairs)}", flush=True)
    print("导入完成", flush=True)


if __name__ == "__main__":
    main()
