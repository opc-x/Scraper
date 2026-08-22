"""收藏 / 归档 —— 用户对抓取结果的标记。

一条职位同时只有一种状态：saved（收藏）或 archived（归档，列表不再展示）。
再次点同一个按钮就是取消。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.scraped import invalidate_scraped_cache
from app.db.connection import get_db
from app.db.schema import JobMark, ScrapedJob

router = APIRouter(prefix="/api/marks", tags=["marks"])

STATES = ("saved", "archived")


class MarkRequest(BaseModel):
    job_id: int | None = None
    channel: str = ""
    external_id: str = ""
    state: str


def _row_dict(m: JobMark) -> dict:
    return {
        "id": m.id,
        "channel": m.channel,
        "external_id": m.external_id,
        "state": m.state,
        "scraped_job_id": m.scraped_job_id,
        "title": m.title,
        "company": m.company,
        "salary": m.salary,
        "city": m.city,
        "skills": m.skills if isinstance(m.skills, list) else [],
        "description": m.description,
        "url": m.url,
        "note": m.note,
        "read_at": m.read_at,
        "created_at": m.created_at,
    }


@router.get("")
def list_marks(
    state: str = Query("", description="saved / archived，留空返回全部"),
    db: Session = Depends(get_db),
):
    if db is None:
        raise HTTPException(503, "Database not configured")
    q = db.query(JobMark)
    if state:
        if state not in STATES:
            raise HTTPException(400, f"state 只能是 {' / '.join(STATES)}")
        q = q.filter_by(state=state)
    rows = q.order_by(JobMark.updated_at.desc()).all()
    return {"marks": [_row_dict(r) for r in rows], "total": len(rows)}


@router.get("/index")
def mark_index(db: Session = Depends(get_db)):
    """前端一次性拿到全部标记，用来在列表上打勾和过滤归档，避免逐条查询。"""
    if db is None:
        raise HTTPException(503, "Database not configured")
    out: dict[str, list[str]] = {"saved": [], "archived": [], "read": []}
    for channel, external_id, state, read_at in db.query(
        JobMark.channel, JobMark.external_id, JobMark.state, JobMark.read_at
    ):
        key = f"{channel}:{external_id}"
        if state in out:
            out[state].append(key)
        if read_at:
            out["read"].append(key)
    return out


@router.post("")
def set_mark(req: MarkRequest, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    if req.state not in STATES:
        raise HTTPException(400, f"state 只能是 {' / '.join(STATES)}")

    job = None
    if req.job_id:
        job = db.query(ScrapedJob).filter_by(id=req.job_id).first()
        if not job:
            raise HTTPException(404, "职位不存在")
        channel, external_id = job.channel, job.external_id
    else:
        channel, external_id = req.channel, req.external_id
        if not channel or not external_id:
            raise HTTPException(400, "要么给 job_id，要么给 channel + external_id")
        job = db.query(ScrapedJob).filter_by(channel=channel, external_id=external_id).first()

    existing = db.query(JobMark).filter_by(channel=channel, external_id=external_id).first()
    if existing and existing.state == req.state:
        # 再点一次同一个按钮 = 取消标记
        db.delete(existing)
        db.commit()
        invalidate_scraped_cache()
        return {"state": None, "message": "已取消"}

    if existing:
        existing.state = req.state
        db.commit()
        invalidate_scraped_cache()
        return {"state": existing.state, "message": "已更新", "id": existing.id}

    mark = JobMark(
        channel=channel,
        external_id=external_id,
        state=req.state,
        scraped_job_id=job.id if job else None,
        title=job.title if job else "",
        company=job.company if job else "",
        salary=job.salary if job else "",
        city=job.city if job else "",
        skills=(job.skills if job and isinstance(job.skills, list) else []),
        description=((job.description or "")[:1000] if job else ""),
        url=job.url if job else "",
    )
    db.add(mark)
    db.commit()
    invalidate_scraped_cache()
    return {"state": mark.state, "message": "已标记", "id": mark.id}


@router.delete("/{mark_id}")
def delete_mark(mark_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(JobMark).filter_by(id=mark_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    invalidate_scraped_cache()
    return {"ok": True}
