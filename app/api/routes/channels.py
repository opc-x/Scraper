from fastapi import APIRouter

from app.core.channel_config import CHANNEL_SCHEMA, load_config

router = APIRouter(prefix="/api", tags=["channels"])


@router.get("/channels")
async def list_channels():
    cfg = load_config()
    channels = []
    for ch_id, schema in CHANNEL_SCHEMA.items():
        ch_cfg = cfg.get(ch_id, {})
        enabled = ch_cfg.get("enabled", False)
        required_fields = [f["key"] for f in schema["fields"] if f.get("required")]
        all_filled = all(bool(ch_cfg.get(k, "")) for k in required_fields)

        if enabled and all_filled:
            status = "active"
        elif enabled:
            status = "missing_config"
        else:
            status = "disabled"

        channels.append({
            "id": ch_id,
            "name": schema["name"],
            "description": schema["description"],
            "status": status,
        })
    return {"channels": channels}
