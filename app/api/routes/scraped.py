import time
from datetime import datetime, timedelta
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.job_derive import TECH_TAGS, china_eligible
from app.core.job_origin import source_label
from app.db.connection import get_db
from app.db.schema import JobMark, ScrapedJob

router = APIRouter(prefix="/api", tags=["scraped"])

_cache: dict[str, tuple[float, dict]] = {}
_cache_ttl = 300
_recent_cache: dict[int, tuple[float, list[ScrapedJob]]] = {}
_catalog_cache: dict[int, tuple[float, list[dict]]] = {}
_archived_cache: tuple[float, set[tuple[str, str]]] | None = None
_recent_lock = Lock()
_catalog_lock = Lock()
KNOWN_CHANNELS = (
    "boss", "hackernews", "telegram", "discord", "x", "x_zh",
    "remoteok", "weworkremotely", "v2ex", "eleduck",
)


def _seen_at():
    """没有原始发布时间就用首次入库时间，避免 BOSS 这类渠道整批从总览消失。"""
    return func.coalesce(ScrapedJob.posted_at, ScrapedJob.first_seen_at, ScrapedJob.last_seen_at)

def invalidate_scraped_cache() -> None:
    global _archived_cache
    _cache.clear()
    _recent_cache.clear()
    _catalog_cache.clear()
    _archived_cache = None


def refresh_archived_flags(db: Session) -> None:
    """归档只改标记，不重打分。"""
    global _archived_cache
    _cache.clear()
    keys = set(db.query(JobMark.channel, JobMark.external_id).filter_by(state="archived").all())
    _archived_cache = (time.monotonic(), keys)
    for _stamp, items in _catalog_cache.values():
        for item in items:
            item["archived"] = (item["channel"], item["payload"]["external_id"]) in keys


def warm_scraped_catalog() -> None:
    from app.db.connection import SessionLocal
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        _catalog(db, 90)
    finally:
        db.close()


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
            ScrapedJob.match_score.between(-1, 100),
            ScrapedJob.data_quality_ok.is_(True),
            _seen_at() >= since,
        ).all()
        _recent_cache[within_days] = (time.monotonic(), rows)
        return rows


def _archived_keys(db: Session) -> set[tuple[str, str]]:
    global _archived_cache
    if _archived_cache and time.monotonic() - _archived_cache[0] < _cache_ttl:
        return _archived_cache[1]
    keys = set(db.query(JobMark.channel, JobMark.external_id).filter_by(state="archived").all())
    _archived_cache = (time.monotonic(), keys)
    return keys


def _index_item(row: ScrapedJob, archived: bool) -> dict:
    payload = _job_dict(row)
    return {
        "channel": row.channel,
        "archived": archived,
        "match_score": row.match_score or 0,
        "value_score": payload["value_score"],
        "salary_hi": row.salary_max_usd or 0,
        "posted": row.posted_at or row.first_seen_at,
        "tags": set(payload["core_tags"]),
        "prefs": {item["key"] for item in payload["interest_tags"]},
        "is_remote": payload["is_remote"],
        "filtered_out": bool(row.filtered_out),
        "value_matched": {
            str(item["label"])
            for item in payload["value_tags"]
            if isinstance(item, dict) and item.get("matched")
        },
        "china_ok": china_eligible(
            is_remote=bool(payload["is_remote"]),
            description=row.description or "",
            city=row.city or "",
        ),
        "payload": payload,
    }


def _catalog(db: Session, within_days: int) -> list[dict]:
    cached = _catalog_cache.get(within_days)
    if cached and time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    with _catalog_lock:
        cached = _catalog_cache.get(within_days)
        if cached and time.monotonic() - cached[0] < _cache_ttl:
            return cached[1]
        archived = _archived_keys(db)
        items = [
            _index_item(row, (row.channel, row.external_id) in archived)
            for row in _recent_rows(db, within_days)
        ]
        _catalog_cache[within_days] = (time.monotonic(), items)
        return items


def _apply_filters(
    items: list[dict],
    *,
    channel: str,
    tag: str,
    preference: str,
    remote: bool | None,
    min_score: int | None,
    include_archived: bool,
    value_tag: str = "",
    china: bool | None = None,
    include_filtered: bool = False,
) -> list[dict]:
    out = items
    if not include_archived:
        out = [item for item in out if not item["archived"]]
    if not include_filtered:
        out = [item for item in out if not item.get("filtered_out")]
    if channel:
        out = [item for item in out if item["channel"] == channel]
    if min_score is not None:
        out = [item for item in out if item["match_score"] >= min_score]
    if preference:
        out = [item for item in out if preference in item["prefs"]]
    if tag:
        needle = tag.lower()
        out = [item for item in out if needle in item["tags"]]
    if remote is not None:
        out = [item for item in out if item["is_remote"] is remote]
    if value_tag:
        out = [item for item in out if value_tag in item.get("value_matched", set())]
    if china is True:
        out = [item for item in out if item.get("china_ok")]
    return out


def _sort_index(items: list[dict], sort: str, reverse: bool) -> None:
    fallback = datetime.min
    if sort == "posted":
        items.sort(key=lambda item: item["posted"] or fallback, reverse=reverse)
    elif sort == "salary":
        items.sort(key=lambda item: (item["salary_hi"], item["match_score"]), reverse=reverse)
    elif sort == "value":
        items.sort(key=lambda item: (item["value_score"], item["match_score"]), reverse=reverse)
    else:
        items.sort(key=lambda item: (item["match_score"], item["posted"] or fallback), reverse=reverse)


def _job_dict(row: ScrapedJob) -> dict:
    """全部字段来自写时预计算好的列（见 app/core/job_derive.py），这里只做取值拼装，
    不再对 title/description 现场跑正则——这是 /api/scraped 曾经卡几秒的根源。"""
    # 展示用的“关键信息”统一从原始 skills + 写入时衍生的 core_tags 合并。
    # 这样抓取、手工添加、Markdown 导入等入口即使适配器没填 skills，也不会漏掉正文里的技术栈。
    raw_skills = row.skills if isinstance(row.skills, list) else []
    core_tags = row.core_tags if isinstance(row.core_tags, list) else []
    skills = list(dict.fromkeys([*(str(x) for x in raw_skills), *(str(x) for x in core_tags)]))
    location = row.city or ""
    if row.is_remote:
        location = location or "Remote"
    return {
        "id": row.id,
        "channel": row.channel,
        "external_id": row.external_id,
        "title": row.title,
        "company": row.company,
        "salary": row.salary,
        "salary_cny": row.salary_cny or "",
        "city": location,
        "skills": skills[:8],
        "core_tags": core_tags,
        "regions": row.regions if isinstance(row.regions, list) else [],
        "is_remote": row.is_remote,
        "interest_tags": row.interest_tags if isinstance(row.interest_tags, list) else [],
        "preference_score": row.preference_score or 0,
        "value_score": row.value_score if row.value_score is not None else 50,
        "value_tags": row.value_tags if isinstance(row.value_tags, list) else [],
        "filtered_out": bool(row.filtered_out),
        "ai_gate_score": row.ai_gate_score,
        "ai_gate_reason": row.ai_gate_reason or "",
        "description": (row.description or "")[:320],
        "url": row.url,
        "source_label": source_label(row.channel, row.raw if isinstance(row.raw, dict) else {}, row.url or ""),
        "match_score": row.match_score,
        "posted_at": row.posted_at,
        "last_seen_at": row.last_seen_at,
    }


@router.get("/scraped")
def list_scraped(
    channel: str = "",
    tag: str = "",
    preference: str = "",
    sort: str = Query("value", pattern="^(match|posted|salary|value)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    remote: bool | None = None,
    value_tag: str = "",
    china: bool | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    within_days: int = Query(90, ge=1, le=90),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    include_archived: bool = False,
    include_filtered: bool = False,
    db: Session = Depends(get_db),
):
    if db is None:
        raise HTTPException(503, "Database not configured")
    key = f"jobs:{channel}:{tag}:{preference}:{sort}:{order}:{remote}:{value_tag}:{china}:{min_score}:{within_days}:{limit}:{offset}:{include_archived}:{include_filtered}"
    cached = _cache.get(key)
    if cached and time.monotonic() - cached[0] < _cache_ttl:
        return cached[1]
    items = list(_apply_filters(
        _catalog(db, within_days),
        channel=channel, tag=tag, preference=preference,
        remote=remote, min_score=min_score, include_archived=include_archived,
        value_tag=value_tag, china=china, include_filtered=include_filtered,
    ))
    _sort_index(items, sort, order == "desc")
    total = len(items)
    page = items[offset:offset + limit]
    result = {
        "jobs": [item["payload"] for item in page],
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
    }
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
    tech_counts = {key: 0 for key in TECH_TAGS}
    for row in eligible:
        for key in row.core_tags if isinstance(row.core_tags, list) else []:
            if key in tech_counts:
                tech_counts[key] += 1
        for item in (row.interest_tags if isinstance(row.interest_tags, list) else []):
            stat = preference_counts.setdefault(
                item["key"], {"key": item["key"], "label": item["label"], "count": 0}
            )
            stat["count"] += 1
    result = {
        "total": sum(item["count"] for item in channels), "channels": channels, "within_days": 90,
        "tech_counts": tech_counts,
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
