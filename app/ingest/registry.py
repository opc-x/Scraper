"""渠道模块注册表。只给 CLI / 测试用，不要让 job_derive import 这里。"""

from __future__ import annotations

from app.ingest import (
    boss,
    discord,
    eleduck,
    hackernews,
    liepin,
    remoteok,
    telegram,
    v2ex,
    weworkremotely,
    x,
    x_zh,
    zhilian,
)
from app.ingest.contract import CHANNEL_LANG, ChannelSpec

_MODULES = (
    boss,
    v2ex,
    eleduck,
    telegram,
    discord,
    x,
    x_zh,
    hackernews,
    remoteok,
    weworkremotely,
    liepin,
    zhilian,
)

CHANNELS = {mod.CHANNEL: mod for mod in _MODULES}


def specs() -> list[ChannelSpec]:
    out: list[ChannelSpec] = []
    for mod in _MODULES:
        expected = CHANNEL_LANG[mod.CHANNEL]
        if expected != mod.LANG:
            raise RuntimeError(f"{mod.CHANNEL}: LANG={mod.LANG} 跟契约 {expected} 不一致")
        out.append(
            ChannelSpec(
                channel=mod.CHANNEL,
                lang=mod.LANG,
                implemented=mod.IMPLEMENTED,
                needs_login=mod.NEEDS_LOGIN,
                title=mod.TITLE,
            )
        )
    return out
