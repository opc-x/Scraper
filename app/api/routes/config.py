from fastapi import APIRouter
from pydantic import BaseModel

from app.core.channel_config import load_config, save_config

router = APIRouter(prefix="/api", tags=["config"])


class ChannelConfigItem(BaseModel):
    enabled: bool = False
    cookie: str = ""


class ChannelConfigUpdate(BaseModel):
    channel: str
    enabled: bool = False
    cookie: str = ""


@router.get("/channels/config")
async def get_config():
    cfg = load_config()
    return {"channels": cfg}


@router.put("/channels/config")
async def update_config(item: ChannelConfigUpdate):
    cfg = load_config()
    if item.channel not in cfg:
        cfg[item.channel] = {}
    cfg[item.channel]["enabled"] = item.enabled
    cfg[item.channel]["cookie"] = item.cookie
    save_config(cfg)
    return {"ok": True, "channel": item.channel}
