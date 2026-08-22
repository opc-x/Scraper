import re
import time
from datetime import datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, tuple_
from sqlalchemy.orm import Session

from app.db.connection import get_db
from app.db.schema import JobMark, ScrapedJob
from app.core.job_quality import evaluate_row, row_data_quality
from app.core.resume import preference_tags
from app.core import salary as salary_lib

router = APIRouter(prefix="/api", tags=["scraped"])

_cache: dict[str, tuple[float, dict]] = {}
_cache_ttl = 300
_recent_cache: dict[int, tuple[float, list[ScrapedJob]]] = {}
_archived_cache: tuple[float, set[tuple[str, str]]] | None = None
_recent_lock = Lock()
KNOWN_CHANNELS = (
    "boss", "hackernews", "telegram", "discord", "x",
    "remoteok", "weworkremotely", "v2ex", "eleduck",
)


def _seen_at():
    """没有原始发布时间就用首次入库时间，避免 BOSS 这类渠道整批从总览消失。"""
    return func.coalesce(ScrapedJob.posted_at, ScrapedJob.first_seen_at, ScrapedJob.last_seen_at)

TECH_TAGS = {
    "java": re.compile(r"\bjava\b", re.I),
    "nodejs": re.compile(r"\b(node(?:\.js|js)?|nestjs)\b", re.I),
    "python": re.compile(r"\b(python|django|fastapi)\b", re.I),
    "agent": re.compile(r"\b(ai agent|agents?|agentic|langchain|crewai)\b", re.I),
    "golang": re.compile(r"\b(go|golang)\b", re.I),
    "rust": re.compile(r"\brust\b", re.I),
    "llm": re.compile(r"\b(llm|large language model|rag)\b", re.I),
}
REGIONS = {
    "US": re.compile(r"\b(US|USA|United States|NYC|San Francisco|California)\b"),
    "EU": re.compile(r"\b(EU|Europe|European Union)\b"),
    "UK": re.compile(r"\b(UK|United Kingdom|London)\b"),
    "Canada": re.compile(r"\bCanada\b"),
    "APAC": re.compile(r"\b(APAC|Asia|India|Singapore|Australia)\b"),
}


def invalidate_scraped_cache() -> None:
    global _archived_cache
    _cache.clear()
    _recent_cache.clear()
    _archived_cache = None


def _recent_rows(db: Session, within_days: int) -> list[ScrapedJob]:
    cached = _recent_cache.get(within_days)
    if cached and time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    with _recent_lock:
        cached = _recent_cache.get(within_days)
        if cached and time.monotonic() - cached[0] < _cache_ttl:
            return cached[1]
        since = datetime.utcnow() - timedelta(days=within_days)
        rows = db.query(ScrapedJob).filter(
            ScrapedJob.match_score.between(-1, 100), _seen_at() >= since
        ).all()
        rows = [row for row in rows if row_data_quality(row)[0]]
        _recent_cache[within_days] = (time.monotonic(), rows)
        return rows


def _archived_keys(db: Session) -> set[tuple[str, str]]:
    global _archived_cache
    if _archived_cache and time.monotonic() - _archived_cache[0] < _cache_ttl:
        return _archived_cache[1]
    keys = set(db.query(JobMark.channel, JobMark.external_id).filter_by(state="archived").all())
    _archived_cache = (time.monotonic(), keys)
    return keys


def _job_dict(row: ScrapedJob) -> dict:
    skills = row.skills if isinstance(row.skills, list) else []
    haystack = " ".join([row.title or "", row.description or "", " ".join(skills)])
    core_tags = [name for name, pattern in TECH_TAGS.items() if pattern.search(haystack)]
    regions = [name for name, pattern in REGIONS.items() if pattern.search(haystack)]
    location = row.city or ""
    remote = bool(re.search(r"remote|远程|worldwide|anywhere", f"{location} {haystack}", re.I))
    if remote:
        location = location or "Remote"
    interest_tags = preference_tags(
        title=row.title or "", description=row.description or "", salary=row.salary or "",
        city=row.city or "", skills=skills,
    )
    return {
        "id": row.id,
        "channel": row.channel,
        "external_id": row.external_id,
        "title": row.title,
        "company": row.company,
        "salary": row.salary,
        "city": location,
        "skills": skills[:8],
        "core_tags": core_tags,
        "regions": regions,
        "is_remote": remote,
        "interest_tags": interest_tags,
        "preference_score": min(100, sum(tag["weight"] for tag in interest_tags)),
        "description": (row.description or "")[:320],
        "url": row.url,
        "match_score": row.match_score,
        "posted_at": row.posted_at,
        "last_seen_at": row.last_seen_at,
    }


def _paged_rows(
    db: Session, *, channel: str, min_score: int | None, within_days: int,
    sort: str, order: str, limit: int, offset: int, include_archived: bool,
) -> tuple[list[ScrapedJob], int]:
    """Paginate the normal list in SQL without downloading every job body."""
    since = datetime.utcnow() - timedelta(days=within_days)
    text = func.lower(ScrapedJob.title + " " + ScrapedJob.description)
    query = db.query(ScrapedJob).filter(
        ScrapedJob.match_score.between(-1, 100),
        _seen_at() >= since,
        func.length(func.trim(ScrapedJob.title)) > 0,
        func.length(func.trim(ScrapedJob.description)) >= 40,
        ~func.lower(func.trim(ScrapedJob.title)).in_(("software engineering", "remote")),
        ~func.lower(ScrapedJob.title).like("http%"),
        ~func.lower(ScrapedJob.title).like("www.%"),
        ~or_(*[
            text.like(f"%{phrase}%") for phrase in (
                "hey job seekers", "job roundup", "weekly jobs", "multiple openings",
                "hiring list", "职位合集", "岗位汇总",
            )
        ]),
    )
    if channel:
        query = query.filter(ScrapedJob.channel == channel)
    if min_score is not None:
        query = query.filter(ScrapedJob.match_score >= min_score)
    if not include_archived:
        archived = _archived_keys(db)
        if archived:
            query = query.filter(~tuple_(ScrapedJob.channel, ScrapedJob.external_id).in_(archived))
    total = query.count()
    primary = ScrapedJob.posted_at if sort == "posted" else ScrapedJob.match_score
    direction = primary.desc if order == "desc" else primary.asc
    tie_breaker = ScrapedJob.id.desc if order == "desc" else ScrapedJob.id.asc
    rows = query.order_by(direction(), tie_breaker()).offset(offset).limit(limit).all()
    return rows, total


@router.get("/scraped")
def list_scraped(
    channel: str = "",
    tag: str = "",
    preference: str = "",
    sort: str = Query("match", pattern="^(match|posted|salary)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    remote: bool | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    within_days: int = Query(90, ge=1, le=90),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    if db is None:
        raise HTTPException(503, "Database not configured")
    key = f"jobs:{channel}:{tag}:{preference}:{sort}:{order}:{remote}:{min_score}:{within_days}:{limit}:{offset}:{include_archived}"
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    if not preference and not tag and remote is None and sort != "salary":
        page, total = _paged_rows(
            db, channel=channel, min_score=min_score, within_days=within_days,
            sort=sort, order=order, limit=limit, offset=offset,
            include_archived=include_archived,
        )
        result = {
            "jobs": [_job_dict(row) for row in page], "offset": offset,
            "total": total, "has_more": offset + limit < total,
        }
        _cache[key] = (time.monotonic(), result)
        return result
    rows = list(_recent_rows(db, within_days))
    if channel:
        rows = [row for row in rows if row.channel == channel]
    if min_score is not None:
        rows = [row for row in rows if row.match_score >= min_score]
    if not include_archived:
        # 归档过的不再出现在列表里
        archived_keys = _archived_keys(db)
        if archived_keys:
            rows = [row for row in rows if (row.channel, row.external_id) not in archived_keys]
    if preference:
        rows = [row for row in rows if preference in {
            item["key"] for item in preference_tags(
                title=row.title or "", description=row.description or "", salary=row.salary or "",
                city=row.city or "", skills=row.skills if isinstance(row.skills, list) else [],
            )
        }]
    reverse = order == "desc"
    if sort == "posted":
        rows.sort(key=lambda row: row.posted_at or row.first_seen_at, reverse=reverse)
    elif sort == "salary":
        rows.sort(key=lambda row: (salary_lib.parse(row.salary or "")[1], row.match_score), reverse=reverse)
    else:
        rows.sort(key=lambda row: (row.match_score, row.posted_at or row.first_seen_at), reverse=reverse)
    if tag:
        rows = [row for row in rows if tag.lower() in _job_dict(row)["core_tags"]]
    if remote is not None:
        rows = [row for row in rows if _job_dict(row)["is_remote"] is remote]
    total = len(rows)
    page = rows[offset:offset + limit]
    jobs = [_job_dict(row) for row in page]
    result = {"jobs": jobs, "offset": offset, "total": total, "has_more": offset + limit < total}
    _cache[key] = (time.monotonic(), result)
    return result


@router.get("/scraped/summary")
def scraped_summary(db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    cached = _cache.get("summary")
    if cached and time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    eligible = _recent_rows(db, 90)
    counts: dict[str, int] = {}
    for row in eligible:
        counts[row.channel] = counts.get(row.channel, 0) + 1
    rows = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    channels = [{"channel": channel, "count": counts.get(channel, 0)} for channel in KNOWN_CHANNELS]
    channels.extend(
        {"channel": channel, "count": count}
        for channel, count in rows
        if channel not in KNOWN_CHANNELS
    )
    preference_counts: dict[str, dict] = {}
    for row in eligible:
        for item in preference_tags(
            title=row.title or "", description=row.description or "", salary=row.salary or "",
            city=row.city or "", skills=row.skills if isinstance(row.skills, list) else [],
        ):
            stat = preference_counts.setdefault(
                item["key"], {"key": item["key"], "label": item["label"], "count": 0}
            )
            stat["count"] += 1
    result = {
        "total": sum(item["count"] for item in channels), "channels": channels, "within_days": 90,
        "preference_counts": sorted(preference_counts.values(), key=lambda item: (-item["count"], item["label"])),
    }
    _cache["summary"] = (time.monotonic(), result)
    return result


@router.delete("/scraped/{job_id}")
def delete_scraped(job_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "Not found")
    db.delete(row)
    db.commit()
    invalidate_scraped_cache()
    return {"ok": True}
