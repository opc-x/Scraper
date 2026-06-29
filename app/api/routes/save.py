from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.models import Job
from app.db.connection import get_db
from app.db.schema import SavedJob

router = APIRouter(prefix="/api", tags=["save"])


@router.post("/save")
async def save_job(job: Job, tags: list[str] = [], db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")

    existing = db.query(SavedJob).filter_by(external_id=f"{job.channel}:{job.external_id}").first()
    if existing:
        raise HTTPException(409, "Job already saved")

    saved = SavedJob(
        channel=job.channel,
        external_id=f"{job.channel}:{job.external_id}",
        title=job.title,
        company=job.company,
        salary=job.salary,
        city=job.city,
        experience=job.experience,
        education=job.education,
        skills=job.skills,
        description=job.description,
        url=job.url,
        raw=job.raw,
        tags=tags,
    )
    db.add(saved)
    db.commit()
    return {"id": saved.id, "message": "saved"}


@router.get("/saved")
async def list_saved(db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    jobs = db.query(SavedJob).order_by(SavedJob.created_at.desc()).all()
    return {"jobs": jobs, "total": len(jobs)}
