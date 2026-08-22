from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from app.core.channel_config import (
    BOARDS,
    CHANNEL_SCHEMA,
    _invalidate_cache,
    load_config,
    save_channel_config,
)
from app.db.connection import engine, get_db
from app.db.schema import ScrapedJob

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/channels/config")
async def get_config():
    cfg = load_config()
    return {"channels": cfg}


@router.get("/channels/schema")
async def get_schema():
    return {"schema": CHANNEL_SCHEMA, "boards": BOARDS}


@router.get("/channels/status")
async def get_channel_status(db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    since = datetime.utcnow() - timedelta(days=90)
    grouped = db.query(
        ScrapedJob.channel,
        func.count(ScrapedJob.id),
        func.sum((ScrapedJob.posted_at >= since).cast(Integer)),
        func.sum(
            ((ScrapedJob.posted_at >= since) & ScrapedJob.match_score.between(0, 100)).cast(Integer)
        ),
        func.max(ScrapedJob.posted_at),
        func.max(ScrapedJob.last_seen_at),
    ).group_by(ScrapedJob.channel).all()
    return {
        "channels": {
            channel: {
                "stored": stored or 0,
                "recent": recent or 0,
                "scored_recent": scored_recent or 0,
                "latest_posted_at": latest_posted_at,
                "last_synced_at": last_synced_at,
            }
            for channel, stored, recent, scored_recent, latest_posted_at, last_synced_at in grouped
        }
    }


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
