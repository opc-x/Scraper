"""RemoteOK。英文渠道。公开 JSON，不登录。"""

from __future__ import annotations

import httpx

from app.adapters.jobboards import fetch_remoteok
from app.core.models import Job
from app.ingest.contract import run_async

CHANNEL = "remoteok"
LANG = "en"
IMPLEMENTED = True
NEEDS_LOGIN = False
TITLE = "RemoteOK"


def pull() -> list[Job]:
    async def _go() -> list[Job]:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await fetch_remoteok(client)

    return run_async(_go())
