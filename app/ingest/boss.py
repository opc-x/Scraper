"""BOSS 直聘。中文渠道。登录态走 Chromium profile。"""

from __future__ import annotations

from app.adapters.boss import BossAdapter
from app.core.models import Job, SearchRequest
from app.ingest.contract import run_async

CHANNEL = "boss"
LANG = "zh"
IMPLEMENTED = True
NEEDS_LOGIN = True
TITLE = "BOSS直聘"


def pull(*, keyword: str = "Java 远程", city: str = "全国", pages: int = 3) -> list[Job]:
    async def _go() -> list[Job]:
        adapter = BossAdapter()
        seen: dict[str, Job] = {}
        try:
            for page in range(1, max(1, pages) + 1):
                batch = await adapter.search(
                    SearchRequest(keyword=keyword, city=city, channel=CHANNEL, page=page),
                )
                for job in batch:
                    seen[job.external_id] = job
                if not batch:
                    break
            return list(seen.values())
        finally:
            await adapter.close()

    return run_async(_go())
