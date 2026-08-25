"""电鸭。中文渠道。公开 JSON API，不登录。"""

from __future__ import annotations

from app.adapters.eleduck import DEFAULT_MAX_AGE_DAYS, EleduckAdapter
from app.core.models import Job
from app.ingest.contract import run_async

CHANNEL = "eleduck"
LANG = "zh"
IMPLEMENTED = True
NEEDS_LOGIN = False
TITLE = "电鸭"


def pull(*, days: int = DEFAULT_MAX_AGE_DAYS, min_jobs: int = 0) -> list[Job]:
    async def _go() -> list[Job]:
        adapter = EleduckAdapter()
        try:
            return await adapter.fetch_recent(
                max_age_days=days, min_jobs=min_jobs,
                java_title_only=True, fetch_details=True,
            )
        finally:
            await adapter.close()

    return run_async(_go())
