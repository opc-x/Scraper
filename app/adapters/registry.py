from app.adapters.base import BaseAdapter
from app.adapters.boss import BossAdapter
from app.adapters.telegram import TelegramAdapter

_adapters: dict[str, BaseAdapter] = {}


def get_adapter(channel: str) -> BaseAdapter:
    if channel not in _adapters:
        match channel:
            case "boss":
                _adapters[channel] = BossAdapter()
            case "telegram":
                _adapters[channel] = TelegramAdapter()
            case _:
                raise ValueError(f"Unknown channel: {channel}")
    return _adapters[channel]


async def close_all():
    for adapter in _adapters.values():
        await adapter.close()
    _adapters.clear()
