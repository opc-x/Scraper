"""职位详情 + 本机 AI 生成的职位画像 + 薪资统计。

画像走本机 claude CLI（订阅额度），符合 CLAUDE.md 里「挖掘/打标签在本机跑」的分工。
生成一次就落库缓存，之后直接读。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import salary as salary_lib
from app.core.job_comments import gather_comments
from app.core.job_profile import profile_fields, render_prompt
from app.core.resume import resume_text
from app.db.connection import get_db
from app.infra.local_ai import run as run_local_ai
from app.api.routes.scraped import _cache, _cache_ttl
from app.db.schema import JobMark, JobProfile, ScrapedJob

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_payload(row: ScrapedJob) -> dict:
    skills = row.skills if isinstance(row.skills, list) else []
    lo, hi = salary_lib.parse(row.salary or "")
    return {
        "id": row.id,
        "channel": row.channel,
        "external_id": row.external_id,
        "title": row.title,
        "company": row.company,
        "salary": row.salary,
        "salary_min_usd": lo,
        "salary_max_usd": hi,
        "salary_bucket": salary_lib.bucket(hi),
        "city": row.city,
        "skills": skills,
        "description": row.description or "",
        "url": row.url,
        "last_seen_at": row.last_seen_at,
    }


@router.get("/salary-stats")
def salary_stats(db: Session = Depends(get_db)):
    """薪资分布统计：按档位分桶 + 按渠道看披露率。"""
    if db is None:
        raise HTTPException(503, "Database not configured")
    import time as _time
    cached = _cache.get("salary-stats")
    if cached and _time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    rows = db.query(ScrapedJob.channel, ScrapedJob.salary).all()

    buckets: dict[str, int] = {k: 0 for k in salary_lib.BUCKET_ORDER}
    by_channel: dict[str, dict] = {}
    values: list[int] = []
    for channel, raw in rows:
        lo, hi = salary_lib.parse(raw or "")
        mid = (lo + hi) // 2 if hi else 0
        buckets[salary_lib.bucket(mid)] = buckets.get(salary_lib.bucket(mid), 0) + 1
        stat = by_channel.setdefault(channel, {"channel": channel, "total": 0, "disclosed": 0, "sum": 0})
        stat["total"] += 1
        if mid:
            stat["disclosed"] += 1
            stat["sum"] += mid
            values.append(mid)

    values.sort()
    n = len(values)
    def pct(p: float) -> int:
        return values[min(n - 1, int(n * p))] if n else 0

    for stat in by_channel.values():
        stat["avg"] = stat["sum"] // stat["disclosed"] if stat["disclosed"] else 0
        stat.pop("sum")

    result = {
        "total": len(rows),
        "disclosed": n,
        "disclose_rate": round(n / len(rows) * 100, 1) if rows else 0,
        "median": pct(0.5),
        "p25": pct(0.25),
        "p75": pct(0.75),
        "max": values[-1] if n else 0,
        "buckets": [{"label": k, "count": buckets.get(k, 0)} for k in salary_lib.BUCKET_ORDER],
        "by_channel": sorted(by_channel.values(), key=lambda x: -x["total"]),
    }
    _cache["salary-stats"] = (_time.monotonic(), result)
    return result


@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    payload = _job_payload(row)

    prof = db.query(JobProfile).filter_by(channel=row.channel, external_id=row.external_id).first()
    payload["profile"] = (prof.profile if prof else None)
    payload["profile_generated_at"] = prof.generated_at if prof else None

    mark = db.query(JobMark).filter_by(channel=row.channel, external_id=row.external_id).first()
    payload["mark_state"] = mark.state if mark else None
    payload["read_at"] = mark.read_at if mark else None
    return payload


@router.post("/{job_id}/profile")
async def generate_profile(job_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")

    existing = db.query(JobProfile).filter_by(channel=row.channel, external_id=row.external_id).first()
    if existing and not refresh:
        return {"profile": existing.profile, "cached": True, "generated_at": existing.generated_at}

    skills = row.skills if isinstance(row.skills, list) else []
    comments, comment_sources = await asyncio.to_thread(
        gather_comments,
        company=row.company, channel=row.channel,
        external_id=row.external_id or "",
        raw=row.raw if isinstance(row.raw, dict) else None,
    )
    prompt = render_prompt(
        resume=resume_text(), title=row.title, company=row.company, salary=row.salary,
        city=row.city, skills=skills, channel=row.channel, description=row.description,
        comments=comments,
    )
    data = await run_local_ai(prompt, engine="claude", timeout=240)
    if not data:
        raise HTTPException(502, "画像生成失败，模型没有返回可解析的结果")
    data["comment_sources"] = comment_sources

    fields = profile_fields(data, row.salary or "")

    target = existing or JobProfile(channel=row.channel, external_id=row.external_id)
    target.scraped_job_id = row.id
    target.verdict = fields["verdict"]
    target.fit_score = fields["fit_score"]
    target.salary_min = fields["salary_min"]
    target.salary_max = fields["salary_max"]
    target.profile = data
    target.model = "claude-cli"
    if not existing:
        db.add(target)
    db.commit()
    return {"profile": data, "cached": False, "generated_at": target.generated_at}


@router.post("/{job_id}/read")
def mark_read(job_id: int, db: Session = Depends(get_db)):
    """标记已阅读 —— 跟收藏/归档独立，不影响列表展示。"""
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    mark = db.query(JobMark).filter_by(channel=row.channel, external_id=row.external_id).first()
    if not mark:
        mark = JobMark(
            channel=row.channel, external_id=row.external_id, state="",
            scraped_job_id=row.id, title=row.title, company=row.company,
            salary=row.salary, city=row.city,
            skills=row.skills if isinstance(row.skills, list) else [],
            description=(row.description or "")[:1000], url=row.url,
        )
        db.add(mark)
    if mark.read_at:
        mark.read_at = None
        db.commit()
        return {"read": False}
    mark.read_at = func.now()
    db.commit()
    return {"read": True}
