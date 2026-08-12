from app.adapters.base import BaseAdapter
from app.adapters.boss import BossAdapter
from app.adapters.discord import DiscordAdapter
from app.adapters.telegram import TelegramAdapter
from app.channels.x import XAdapter
from app.channels.youtube import YouTubeAdapter

_adapters: dict[str, BaseAdapter] = {}


def get_adapter(channel: str) -> BaseAdapter:
    if channel not in _adapters:
        match channel:
            case "boss":
                _adapters[channel] = BossAdapter()
            case "telegram":
                _adapters[channel] = TelegramAdapter()
            case "discord":
                _adapters[channel] = DiscordAdapter()
            case "x":
                _adapters[channel] = XAdapter()
            case "youtube":
                _adapters[channel] = YouTubeAdapter()
            case _:
                raise ValueError(f"Unknown channel: {channel}")
    return _adapters[channel]


async def close_all():
    for adapter in _adapters.values():
        await adapter.close()
    _adapters.clear()
