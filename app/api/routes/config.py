from fastapi import APIRouter, HTTPException

from app.core.channel_config import CHANNEL_SCHEMA, load_config, save_channel_config

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/channels/config")
async def get_config():
    cfg = load_config()
    return {"channels": cfg}


@router.get("/channels/schema")
async def get_schema():
    return {"schema": CHANNEL_SCHEMA}


@router.put("/channels/config")
async def update_config(body: dict):
    channel = body.get("channel")
    if not channel or channel not in CHANNEL_SCHEMA:
        raise HTTPException(400, f"Unknown channel: {channel}")

    schema = CHANNEL_SCHEMA[channel]
    valid_keys = {"enabled"} | {f["key"] for f in schema["fields"]}

    filtered = {}
    for k, v in body.items():
        if k == "channel":
            continue
        if k in valid_keys:
            filtered[k] = v

    save_channel_config(channel, filtered)
    return {"ok": True, "channel": channel}
