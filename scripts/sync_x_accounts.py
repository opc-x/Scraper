"""同步 X 账号档案表（x_accounts）：给定一批 screen_name，抓真实 profile 写库。

用法：python -m scripts.sync_x_accounts handle1 handle2 ...
不传参数则同步 mined_accounts 表里 channel=x 的全部账号。
"""
import asyncio
import logging
import sys

from app.channels.x import XAdapter
from app.db.connection import SessionLocal
from app.db.persist import persist_x_accounts, profile_to_x_account_fields
from app.db.schema import MinedAccount

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _handles_from_mined_accounts() -> list[str]:
    db = SessionLocal()
    try:
        rows = db.query(MinedAccount.handle).filter_by(channel="x").distinct().all()
        return [r[0] for r in rows]
    finally:
        db.close()


def main(handles: list[str]):
    adapter = XAdapter()
    rows = []
    try:
        for h in handles:
            profile = adapter.fetch_user_profile_sync(h, timeout=12)
            if not profile:
                logger.warning("拿不到 %s 的 profile，跳过", h)
                continue
            rows.append(profile_to_x_account_fields(h, profile))
            logger.info("%s: 粉丝 %s, 发帖 %s", h, rows[-1]["followers_count"], rows[-1]["tweets_count"])
    finally:
        asyncio.run(adapter.close())

    persist_x_accounts(rows)
    logger.info("写入 %d 个账号档案", len(rows))


if __name__ == "__main__":
    handles = sys.argv[1:] or _handles_from_mined_accounts()
    main(handles)
