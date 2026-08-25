"""Discord。英文渠道。Python 入口吃 dump；浏览器扒帖是 scrape.js，不是这个文件。"""

from __future__ import annotations

from pathlib import Path

from app.core.models import Job
from scripts.import_discord_dump import _iter_jobs, _to_job

CHANNEL = "discord"
LANG = "en"
IMPLEMENTED = True
NEEDS_LOGIN = True
TITLE = "Discord"

DUMPS = (
    Path("/tmp/discord_thread_dump.jsonl"),
    Path("data/discord_jobs_full.jsonl"),
)


def pull(*, path: str = "") -> list[Job]:
    dump = Path(path) if path else next((p for p in DUMPS if p.exists() and p.stat().st_size), None)
    if dump is None:
        raise FileNotFoundError("没有 Discord dump，先跑 scripts/discord_unattended_scrape.js")
    return [job for item in _iter_jobs(dump) if (job := _to_job(item))]
