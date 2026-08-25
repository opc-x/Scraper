from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.channel_config import CHANNEL_SCHEMA, load_config
from app.db.connection import get_db
from app.db.schema import ChannelSyncRun

router = APIRouter(prefix="/api", tags=["channels"])

SYNC_COVERAGE = {
    "boss": "每个派生词最多 10 页；无可靠发布时间，报告会标明覆盖不足",
    "telegram": "按消息时间滚动到查询截止日",
    "discord": "按消息时间分页到查询截止日",
    "x": "实时搜索首屏；受风控限制，报告会标明覆盖不足",
    "x_zh": "中文全站搜索近 90 天；登录态与 X 英文共用",
    "v2ex": "公开 Atom 最新 50 条；报告会标明覆盖不足",
    "eleduck": "按查询天数翻页，直到发布时间截止",
}


@router.get("/channels")
async def list_channels(db: Session = Depends(get_db)):
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
            "board": schema.get("board", ""),
            "description": schema["description"],
            "status": status,
            "sync_supported": ch_id in SYNC_COVERAGE,
            "sync_coverage": SYNC_COVERAGE.get(ch_id, "该渠道尚未接入手动拉取"),
            "last_sync": _latest_sync(db, ch_id),
        })
    return {"channels": channels}


def _latest_sync(db: Session, channel: str) -> dict | None:
    run = (
        db.query(ChannelSyncRun)
        .filter_by(channel=channel)
        .order_by(ChannelSyncRun.id.desc())
        .first()
    )
    if not run:
        return None
    return {
        "status": run.status,
        "pulled": run.pulled,
        "finished_at": run.finished_at,
        "error": run.error,
    }
