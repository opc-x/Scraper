"""Hacker News Who is hiring。英文渠道。Algolia 公开 API，不登录。"""

from __future__ import annotations

import time

from app.core.models import Job
from scripts.import_job_json import to_job
from scripts.mine_hn_hiring import fetch, hiring_threads, parse_post

CHANNEL = "hackernews"
LANG = "en"
IMPLEMENTED = True
NEEDS_LOGIN = False
TITLE = "Hacker News"


def pull(*, months: int = 3, limit: int = 0, remote_only: bool = True) -> list[Job]:
    rows: list[Job] = []
    for thread in hiring_threads(months):
        item = fetch(f"https://hn.algolia.com/api/v1/items/{thread['objectID']}")
        for child in item.get("children") or []:
            row = parse_post(child, thread)
            if not row:
                continue
            if remote_only and not row["is_remote"]:
                continue
            job, _posted = to_job(row, CHANNEL)
            if job.external_id:
                rows.append(job)
        time.sleep(0.4)
    if limit:
        rows = rows[:limit]
    return rows
