"""猎聘。中文渠道。CHANNEL_SCHEMA 有配置，registry 没有 adapter。"""

from __future__ import annotations

from app.core.models import Job

CHANNEL = "liepin"
LANG = "zh"
IMPLEMENTED = False
NEEDS_LOGIN = True
TITLE = "猎聘"


def pull(**_kwargs) -> list[Job]:
    raise NotImplementedError("liepin: 配了没接，registry 里没有 adapter")
