from fastapi import APIRouter

from app.core.channel_config import load_config

router = APIRouter(prefix="/api", tags=["channels"])

CHANNEL_META = {
    "boss": {"name": "BOSS直聘", "description": "综合流量王，直聊快，互联网/新消费/中小企业"},
    "liepin": {"name": "猎聘", "description": "3年+中高端，猎头资源"},
    "zhilian": {"name": "智联招聘", "description": "国企央企/金融地产，传统行业"},
}


@router.get("/channels")
async def list_channels():
    cfg = load_config()
    channels = []
    for ch_id, meta in CHANNEL_META.items():
        ch_cfg = cfg.get(ch_id, {})
        enabled = ch_cfg.get("enabled", False)
        has_cookie = bool(ch_cfg.get("cookie", ""))
        if enabled and has_cookie:
            status = "active"
        elif enabled:
            status = "no_cookie"
        else:
            status = "planned"
        channels.append({"id": ch_id, "status": status, **meta})
    return {"channels": channels}
