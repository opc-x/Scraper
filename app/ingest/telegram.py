"""Telegram。例外：中英文都要。公开频道网页预览，不登录。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from app.core.models import Job
from scripts.mine_telegram_jobs import SRC, crawl_channel

CHANNEL = "telegram"
LANG = "both"
IMPLEMENTED = True
NEEDS_LOGIN = False
TITLE = "Telegram"


def pull(*, pages: int = 15, channels: str = "", workers: int = 8) -> list[Job]:
    if channels:
        names = [c.strip() for c in channels.split(",") if c.strip()]
    else:
        names = [c["username"] for c in json.loads(SRC.read_text(encoding="utf-8"))]
    all_jobs: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for jobs in pool.map(lambda n: crawl_channel(n, pages), names):
            all_jobs.extend(jobs)
    dedup = {row["external_id"]: row for row in all_jobs}
    return [Job(**row) for row in dedup.values()]
