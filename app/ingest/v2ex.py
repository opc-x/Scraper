"""V2EX 酷工作。中文渠道。公开 Atom，不登录。"""

from __future__ import annotations

from app.adapters.v2ex import V2exAdapter
from app.core.models import Job
from app.ingest.contract import run_async

CHANNEL = "v2ex"
LANG = "zh"
IMPLEMENTED = True
NEEDS_LOGIN = False
TITLE = "V2EX"


def pull(*, days: int = 90) -> list[Job]:
    async def _go() -> list[Job]:
        adapter = V2exAdapter()
        try:
            # adapter 负责完整覆盖近 N 天酷工作节点；方向等入库条件由统一 persist gate 裁定。
            return await adapter.fetch_java_recent(max_age_days=days)
        finally:
            await adapter.close()

    return run_async(_go())
