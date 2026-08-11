from fastapi import APIRouter, HTTPException

from app.core.channel_config import BOARDS, CHANNEL_SCHEMA, _invalidate_cache, load_config, save_channel_config
from app.db.connection import engine

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/channels/config")
async def get_config():
    cfg = load_config()
    return {"channels": cfg}


@router.get("/channels/schema")
async def get_schema():
    return {"schema": CHANNEL_SCHEMA, "boards": BOARDS}


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


@router.delete("/channels/config/{channel}")
async def reset_config(channel: str):
    if channel not in CHANNEL_SCHEMA:
        raise HTTPException(400, f"Unknown channel: {channel}")
    if not engine:
        raise HTTPException(503, "Database not configured")

    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM channel_configs WHERE channel = :ch"), {"ch": channel})
    _invalidate_cache()
    return {"ok": True, "channel": channel}
