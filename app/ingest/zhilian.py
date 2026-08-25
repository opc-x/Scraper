"""智联。中文渠道。CHANNEL_SCHEMA 有配置，registry 没有 adapter。"""

from __future__ import annotations

from app.core.models import Job

CHANNEL = "zhilian"
LANG = "zh"
IMPLEMENTED = False
NEEDS_LOGIN = True
TITLE = "智联招聘"


def pull(**_kwargs) -> list[Job]:
    raise NotImplementedError("zhilian: 配了没接，registry 里没有 adapter")
