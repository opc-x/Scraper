from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.schema import ScrapedJob

router = APIRouter(prefix="/api", tags=["scraped"])


@router.get("/scraped")
async def list_scraped(channel: str = "", limit: int = 100, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    q = db.query(ScrapedJob)
    if channel:
        q = q.filter_by(channel=channel)
    rows = q.order_by(ScrapedJob.last_seen_at.desc()).limit(min(limit, 500)).all()
    return {"jobs": rows, "total": len(rows)}


@router.delete("/scraped/{job_id}")
async def delete_scraped(job_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
