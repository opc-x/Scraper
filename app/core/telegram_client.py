import logging

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.core.channel_config import get_channel_config

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None
_connected: bool = False


async def get_telegram_client() -> TelegramClient | None:
    global _client, _connected

    cfg = get_channel_config("telegram")
    api_id = cfg.get("api_id", "")
    api_hash = cfg.get("api_hash", "")

    if not api_id or not api_hash:
        return None

    if _client and _connected:
        return _client

    session_str = cfg.get("_session", "")
    if not session_str:
        return None

    session = StringSession(session_str)
    _client = TelegramClient(session, int(api_id), api_hash)
    await _client.connect()

    if not await _client.is_user_authorized():
        return None

    _connected = True
    return _client


async def close_telegram_client():
    global _client, _connected
    if _client:
        await _client.disconnect()
        _client = None
        _connected = False
