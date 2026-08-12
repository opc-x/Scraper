from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.schema import MinedAccount

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/accounts")
async def list_accounts(
    channel: str = "", topic: str = "", kept_only: bool = True, limit: int = 200, db: Session = Depends(get_db)
):
    if db is None:
        raise HTTPException(503, "Database not configured")
    q = db.query(MinedAccount)
    if channel:
        q = q.filter_by(channel=channel)
    if topic:
        q = q.filter_by(topic=topic)
    if kept_only:
        q = q.filter_by(kept=True)
    rows = q.order_by(MinedAccount.confidence.desc()).limit(min(limit, 500)).all()
    return {"accounts": rows, "total": len(rows)}


@router.get("/accounts/topics")
async def list_topics(channel: str = "", db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    q = db.query(MinedAccount.channel, MinedAccount.topic).distinct()
    if channel:
        q = q.filter_by(channel=channel)
    rows = q.all()
    return {"topics": [{"channel": r[0], "topic": r[1]} for r in rows]}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(MinedAccount).filter_by(id=account_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
