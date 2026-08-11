import logging

from app.core.models import Job
from app.db.connection import SessionLocal
from app.db.schema import ScrapedJob

logger = logging.getLogger(__name__)


def persist_scraped_jobs(jobs: list[Job]) -> None:
    if not SessionLocal or not jobs:
        return

    db = SessionLocal()
    try:
        for job in jobs:
            existing = (
                db.query(ScrapedJob)
                .filter_by(channel=job.channel, external_id=job.external_id)
                .first()
            )
            if existing:
                existing.title = job.title
                existing.company = job.company
                existing.salary = job.salary
                existing.city = job.city
                existing.experience = job.experience
                existing.education = job.education
                existing.skills = job.skills
                existing.description = job.description
                existing.url = job.url
                existing.raw = job.raw
            else:
                db.add(
                    ScrapedJob(
                        channel=job.channel,
                        external_id=job.external_id,
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
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist scraped jobs: %s", e)
    finally:
        db.close()
