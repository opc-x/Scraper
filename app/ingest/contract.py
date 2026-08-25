"""职位拉取契约：渠道名、语言口径、pull() → list[Job]。

这个模块不能 import persist / job_derive，避免循环依赖。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from app.core.models import Job

Lang = Literal["zh", "en", "both"]

# 中文渠道用中文规则，英文渠道用英文规则，Telegram 中英文都要。
CHANNEL_LANG: dict[str, Lang] = {
    "boss": "zh",
    "v2ex": "zh",
    "eleduck": "zh",
    "liepin": "zh",
    "zhilian": "zh",
    "discord": "en",
    "x": "en",
    "x_zh": "zh",
    "hackernews": "en",
    "remoteok": "en",
    "weworkremotely": "en",
    "telegram": "both",
}


def lang_for(channel: str) -> Lang:
    ch = (channel or "").strip().lower()
    if ch in {"jobboards", "remoteok", "weworkremotely"}:
        return "en"
    return CHANNEL_LANG.get(ch, "both")


@dataclass(frozen=True)
class ChannelSpec:
    channel: str
    lang: Lang
    implemented: bool
    needs_login: bool
    title: str


@dataclass(frozen=True)
class PullResult:
    channel: str
    fetched: int
    persisted: int


def run_async(coro):
    return asyncio.run(coro)


def persist_jobs(jobs: list[Job], *, lens_only: bool = True) -> int:
    from app.db.persist import persist_scraped_jobs

    # persist 里会跑 job_rules.evaluate_ingest_gate（系统规则 → 入库）再按口径落库
    written = persist_scraped_jobs(jobs, lens_only=lens_only)
    return written


def run_module(mod, *, persist: bool = True, lens_only: bool = True, **kwargs) -> PullResult:
    import inspect

    if not getattr(mod, "IMPLEMENTED", True):
        raise NotImplementedError(f"{mod.CHANNEL}: 还没接 adapter，不能拉")
    allowed = inspect.signature(mod.pull).parameters
    jobs: list[Job] = mod.pull(**{k: v for k, v in kwargs.items() if k in allowed})
    written = persist_jobs(jobs, lens_only=lens_only) if persist and jobs else 0
    return PullResult(channel=mod.CHANNEL, fetched=len(jobs), persisted=written)
