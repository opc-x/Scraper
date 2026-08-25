"""职位拉取入口包。一渠道一文件，语言口径在 contract.CHANNEL_LANG。

YouTube 不在这里：那是面试素材，不是职位源。
本文件不能 import 各渠道模块，否则 job_derive → ingest → persist 会环。
渠道清单走 app.ingest.registry。
"""

from app.ingest.contract import CHANNEL_LANG, ChannelSpec, PullResult, lang_for, run_module

__all__ = ["CHANNEL_LANG", "ChannelSpec", "PullResult", "lang_for", "run_module"]
