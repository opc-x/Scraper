"""职位详情 + 本机 AI 生成的职位画像 + 薪资统计。

画像走本机 claude CLI（订阅额度），符合 CLAUDE.md 里「挖掘/打标签在本机跑」的分工。
生成一次就落库缓存，之后直接读。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.adapters.boss import BossAdapter
from app.core import manual_job
from app.core import salary as salary_lib
from app.core import value_tags as value_tags_lib
from app.core.job_comments import gather_comments
from app.core.job_origin import source_label
from app.core.job_derive import _gap_tags, evaluate_ingest_gate, recompute_value_scores
from app.core.models import Job
from pydantic import BaseModel

from app.core.job_ask import ACTIONS, job_context, normalize_reply, profile_to_reply, render_ask_prompt
from app.core.job_profile import profile_fields, render_prompt
from app.core.resume import resume_text
from app.db.connection import get_db
from app.db.persist import persist_scraped_jobs
from app.infra.local_ai import LocalAiError, run as run_local_ai
from app.api.routes.scraped import _cache, _cache_ttl, invalidate_scraped_cache
from app.db.schema import JobMark, JobProfile, ScrapedJob

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _run_ai(prompt: str, **kwargs) -> dict:
    try:
        return await run_local_ai(prompt, **kwargs)
    except LocalAiError as exc:
        raise HTTPException(502, str(exc)) from exc


def _raw_dict(row: ScrapedJob) -> dict:
    return row.raw if isinstance(row.raw, dict) else {}


def _job_extras(row: ScrapedJob) -> dict:
    """列表接口就有、详情页却没露出来的字段（经验/区域/公司规模/福利/招聘官）。"""
    raw = _raw_dict(row)
    welfare = raw.get("welfareList") if isinstance(raw.get("welfareList"), list) else []
    return {
        "experience": row.experience or raw.get("jobExperience") or "",
        "education": row.education or raw.get("jobDegree") or "",
        "district": " ".join(x for x in (raw.get("areaDistrict"), raw.get("businessDistrict")) if x),
        "industry": raw.get("brandIndustry") or "",
        "stage": raw.get("brandStageName") or "",
        "scale": raw.get("brandScaleName") or "",
        "welfare": [str(x) for x in welfare if x],
        "recruiter": " ".join(x for x in (raw.get("bossName"), raw.get("bossTitle")) if x),
    }


def _job_payload(row: ScrapedJob) -> dict:
    skills = row.skills if isinstance(row.skills, list) else []
    lo = row.salary_min_usd or 0
    hi = row.salary_max_usd or 0
    if not hi:
        lo, hi = salary_lib.parse(row.salary or "")
    extras = _job_extras(row)
    raw = _raw_dict(row)
    sections = raw.get("sections") if isinstance(raw.get("sections"), list) else []
    return {
        "id": row.id,
        "channel": row.channel,
        "external_id": row.external_id,
        "title": row.title,
        "company": row.company,
        "salary": row.salary,
        "salary_cny": row.salary_cny or salary_lib.format_cny(
            lo, hi, salary_text=row.salary or "",
        ),
        "salary_min_usd": lo,
        "salary_max_usd": hi,
        "salary_bucket": row.salary_bucket or salary_lib.bucket(hi),
        "city": row.city,
        "is_remote": bool(row.is_remote),
        "experience": extras["experience"],
        "education": extras["education"],
        "district": extras["district"],
        "industry": extras["industry"],
        "stage": extras["stage"],
        "scale": extras["scale"],
        "welfare": extras["welfare"],
        "recruiter": extras["recruiter"],
        "skills": skills,
        "description": row.description or "",
        "sections": [
            {"title": str(s.get("title") or "").strip(), "body": str(s.get("body") or "").strip()}
            for s in sections
            if isinstance(s, dict) and str(s.get("title") or "").strip() and str(s.get("body") or "").strip()
        ],
        "company_intro": raw.get("brandIntroduce") or "",
        "url": row.url,
        "source_label": source_label(row.channel, raw, row.url or ""),
        "match_score": row.match_score if row.match_score is not None else -1,
        "value_score": row.value_score if row.value_score is not None else 50,
        "posted_at": row.posted_at,
        "last_seen_at": row.last_seen_at,
        "has_real_jd": BossAdapter.has_real_jd(row.description or "", raw),
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


def _hydrate_boss_if_needed(row: ScrapedJob, db: Session) -> None:
    if row.channel != "boss":
        return
    raw = _raw_dict(row)
    if BossAdapter.has_real_jd(row.description or "", raw):
        return
    parsed = BossAdapter.fetch_job_detail(
        security_id=str(raw.get("securityId") or ""),
        encrypt_job_id=row.external_id or "",
        lid=str(raw.get("lid") or ""),
    )
    if not BossAdapter.apply_detail(row, parsed):
        return
    db.commit()
    invalidate_scraped_cache()


@router.get("/{job_id}")
def job_detail(job_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    try:
        _hydrate_boss_if_needed(row, db)
    except Exception as exc:
        logger.warning("boss hydrate skipped: %s", exc)
        db.rollback()
        row = db.query(ScrapedJob).filter_by(id=job_id).first()
    payload = _job_payload(row)

    prof = db.query(JobProfile).filter_by(channel=row.channel, external_id=row.external_id).first()
    payload["profile"] = (prof.profile if prof else None)
    payload["profile_generated_at"] = prof.generated_at if prof else None

    mark = db.query(JobMark).filter_by(channel=row.channel, external_id=row.external_id).first()
    payload["mark_state"] = mark.state if mark else None
    payload["read_at"] = mark.read_at if mark else None

    skills = row.skills if isinstance(row.skills, list) else []
    value_score, value_hits = value_tags_lib.score_job(
        db, channel=row.channel, external_id=row.external_id,
        title=row.title or "", description=row.description or "",
        city=row.city or "", skills=skills, salary=row.salary or "",
    )
    _, gate = evaluate_ingest_gate(
        title=row.title or "", description=row.description or "",
        city=row.city or "", is_remote=bool(row.is_remote), skills=skills,
        channel=row.channel or "", posted_at=row.posted_at,
    )
    gap_tags = _gap_tags(gate.get("signals") or {})
    payload["value_score"] = value_score
    payload["value_tags"] = gap_tags + value_hits
    hit_by_id = {h["id"]: h for h in value_hits}
    payload["value_tag_library"] = [
        {
            "id": t.id,
            "label": t.label,
            "category": t.category,
            "polarity": t.polarity,
            "weight": t.weight,
            "auto": bool(hit_by_id.get(t.id, {}).get("auto")),
            "manual": bool(hit_by_id.get(t.id, {}).get("manual")),
            "applied": bool(hit_by_id.get(t.id, {}).get("matched")),
            "pinned": bool(getattr(t, "pinned", False)),
            "matched": bool(hit_by_id.get(t.id, {}).get("matched")),
            "source": hit_by_id.get(t.id, {}).get("source"),
        }
        for t in value_tags_lib.list_approved(db)
    ]
    return payload


class ValueTagToggleRequest(BaseModel):
    on: bool


class AiTagRequest(BaseModel):
    message: str


@router.post("/{job_id}/ai-tag")
async def ai_tag_job(job_id: int, body: AiTagRequest, db: Session = Depends(get_db)):
    """用户写一句判断，本机 AI 对照职位原文匹配已有价值观标签，命中的写入手动打标。"""
    if db is None:
        raise HTTPException(503, "Database not configured")
    note = (body.message or "").strip()
    if not note:
        raise HTTPException(400, "先写一句再打标")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    try:
        _hydrate_boss_if_needed(row, db)
    except Exception as exc:
        logger.warning("boss hydrate skipped: %s", exc)
        db.rollback()
        row = db.query(ScrapedJob).filter_by(id=job_id).first()
        if not row:
            raise HTTPException(404, "职位不存在")

    from app.core.value_tag_match import catalog_text, parse_tag_ids, render_prompt

    tags = value_tags_lib.list_approved(db)
    if not tags:
        return {"applied": [], "skipped": []}
    allowed = {t.id: t for t in tags}
    skills = row.skills if isinstance(row.skills, list) else []
    _, hits = value_tags_lib.score_job(
        db, channel=row.channel, external_id=row.external_id,
        title=row.title or "", description=row.description or "",
        city=row.city or "", skills=skills, salary=row.salary or "",
    )
    already = {h["id"] for h in hits if h["matched"]}
    prompt = render_prompt(
        catalog=catalog_text(tags),
        job=job_context(
            title=row.title or "",
            company=row.company or "",
            salary=row.salary or "",
            city=row.city or "",
            skills=skills,
            channel=row.channel,
            description=row.description or "",
        ),
        note=note,
    )
    data = await _run_ai(prompt, timeout=90)
    chosen = parse_tag_ids(data, set(allowed))
    applied: list[dict] = []
    skipped: list[dict] = []
    for tag_id in chosen:
        tag = allowed[tag_id]
        item = {"id": tag.id, "label": tag.label}
        if tag_id in already:
            skipped.append(item)
            continue
        value_tags_lib.set_manual_tag(
            db, channel=row.channel, external_id=row.external_id, tag_id=tag_id, on=True, source="ai_assist",
        )
        already.add(tag_id)
        applied.append(item)
    if applied:
        recompute_value_scores(db, channel=row.channel, external_id=row.external_id)
        invalidate_scraped_cache()
    return {"applied": applied, "skipped": skipped}


@router.post("/{job_id}/value-tags/{tag_id}")
def toggle_job_value_tag(job_id: int, tag_id: int, body: ValueTagToggleRequest, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    value_tags_lib.set_manual_tag(
        db, channel=row.channel, external_id=row.external_id, tag_id=tag_id, on=body.on, source="manual",
    )
    recompute_value_scores(db, channel=row.channel, external_id=row.external_id)
    invalidate_scraped_cache()
    return {"ok": True}


class AskRequest(BaseModel):
    action: str
    message: str = ""
    refresh: bool = False


@router.post("/{job_id}/ask")
async def ask_job(job_id: int, body: AskRequest, db: Session = Depends(get_db)):
    """详情页 AI 动作：特征 / 价值观 / 要求 / 偏好 / 简历 / 自由问。"""
    if db is None:
        raise HTTPException(503, "Database not configured")
    if body.action not in ACTIONS:
        raise HTTPException(400, f"未知动作: {body.action}")
    row = db.query(ScrapedJob).filter_by(id=job_id).first()
    if not row:
        raise HTTPException(404, "职位不存在")
    try:
        _hydrate_boss_if_needed(row, db)
    except Exception as exc:
        logger.warning("boss hydrate skipped: %s", exc)
        db.rollback()
        row = db.query(ScrapedJob).filter_by(id=job_id).first()
        if not row:
            raise HTTPException(404, "职位不存在")

    if body.action == "resume":
        force = body.refresh or any(k in (body.message or "") for k in ("重新", "刷新"))
        existing = db.query(JobProfile).filter_by(channel=row.channel, external_id=row.external_id).first()
        if existing and not force:
            return profile_to_reply(existing.profile if isinstance(existing.profile, dict) else {})
        try:
            generated = await generate_profile(job_id, refresh=True, db=db)
        except HTTPException:
            raise
        except Exception:
            logger.exception("resume generate failed")
            raise HTTPException(502, "简历匹配失败，本机模型没跑起来")
        return {**profile_to_reply(generated.get("profile") or {}), "cached": False}

    skills = row.skills if isinstance(row.skills, list) else []
    prompt = render_ask_prompt(
        action=body.action,
        context=job_context(
            title=row.title or "",
            company=row.company or "",
            salary=row.salary or "",
            city=row.city or "",
            skills=skills,
            channel=row.channel,
            description=row.description or "",
        ),
        resume=resume_text(),
        message=body.message or "",
    )
    data = await _run_ai(prompt, timeout=180)
    return normalize_reply(data, body.action)


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
    data = await _run_ai(prompt, engine="claude", timeout=240)
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


class ManualJobRequest(BaseModel):
    mode: str  # "text" | "url" | "markdown"
    content: str
    engine: str | None = None  # "codex" | "claude" | "cursor-agent"


async def _fetch_url_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as http:
            res = await http.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Scraper/1.0)"})
            res.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            422,
            f"链接能连上但返回 {e.response.status_code}，打不开正文。改粘贴原文，或放到 Markdown 文件里批量导入。",
        ) from e
    except httpx.HTTPError:
        raise HTTPException(
            422,
            "打不开这个链接（超时、被墙或站点拦爬虫）。改粘贴原文，或放到 Markdown 文件里用 --- 分隔批量导入。",
        )
    text = manual_job.html_to_text(res.text)
    if not text.strip():
        raise HTTPException(422, "链接打开了但抠不出正文，改粘贴原文吧。")
    return text


async def _ingest_manual_text(
    *,
    raw_text: str,
    source_url: str,
    engine: str | None,
    resume: str,
    db: Session,
) -> int:
    from app.core.value_tag_match import catalog_text, parse_tag_ids

    approved_tags = value_tags_lib.list_approved(db)
    allowed_tag_ids = {tag.id for tag in approved_tags}
    prompt = manual_job.render_prompt(
        raw_text, resume=resume, catalog=catalog_text(approved_tags),
    )
    data = await _run_ai(prompt, engine=engine, timeout=180)
    ingest_tag_ids = parse_tag_ids(
        {"tag_ids": data.get("value_tag_ids") if isinstance(data, dict) else []},
        allowed_tag_ids,
    )

    fields = manual_job.job_fields(data)
    if not fields["title"]:
        raise HTTPException(422, "没识别出职位信息，确认内容里包含真实招聘信息")

    match = manual_job.match_fields(data)
    raw = {**data, **manual_job.extras_for_raw(data)}
    external_id = hashlib.sha1((source_url or raw_text).encode("utf-8")).hexdigest()[:32]
    job = Job(
        channel="manual", external_id=external_id, url=source_url,
        raw=raw, **fields,
    )
    await asyncio.to_thread(persist_scraped_jobs, [job])

    row = db.query(ScrapedJob).filter_by(channel="manual", external_id=external_id).first()
    if not row:
        raise HTTPException(500, "落库失败")

    for tag_id in ingest_tag_ids:
        value_tags_lib.set_manual_tag(
            db, channel=row.channel, external_id=row.external_id,
            tag_id=tag_id, on=True, source="ai_ingest",
        )
    if ingest_tag_ids:
        recompute_value_scores(db, channel=row.channel, external_id=row.external_id)

    from app.core import match_score as match_score_lib

    breakdown = match_score_lib.compose(
        match["fit_score"],
        title=row.title or "",
        description=row.description or "",
        city=row.city or "",
        skills=row.skills if isinstance(row.skills, list) else [],
        one_liner=match["one_liner"],
    )
    row.match_score = breakdown.score
    if raw.get("is_remote_hint"):
        row.is_remote = True
    if not (row.salary_cny or "").strip():
        row.salary_cny = salary_lib.format_cny(
            row.salary_min_usd or 0, row.salary_max_usd or 0, salary_text=row.salary or "",
        )
    lo, hi = salary_lib.parse(row.salary or "")
    if match["salary_min_usd"] or match["salary_max_usd"]:
        lo = match["salary_min_usd"] or lo
        hi = match["salary_max_usd"] or hi
    if not (row.salary_cny or "").strip():
        row.salary_cny = salary_lib.format_cny(lo, hi)
    prof = db.query(JobProfile).filter_by(channel=row.channel, external_id=row.external_id).first()
    profile_body = {
        "verdict": breakdown.verdict,
        "fit_score": breakdown.score,
        "llm_fit_score": breakdown.llm_score,
        "rule_score": breakdown.rule_score,
        "score_caps": list(breakdown.caps),
        "score_evidence": list(breakdown.evidence),
        "one_liner": match["one_liner"],
        "salary_min_usd": lo,
        "salary_max_usd": hi,
        "salary_cny": row.salary_cny,
    }
    if not prof:
        prof = JobProfile(channel=row.channel, external_id=row.external_id)
        db.add(prof)
    prof.scraped_job_id = row.id
    prof.verdict = breakdown.verdict
    prof.fit_score = breakdown.score
    prof.salary_min = lo
    prof.salary_max = hi
    prof.profile = {**(prof.profile if isinstance(prof.profile, dict) else {}), **profile_body}
    prof.model = engine or "local-ai"
    db.commit()
    return row.id


@router.post("/manual")
async def add_manual_job(body: ManualJobRequest, db: Session = Depends(get_db)):
    """手工录入：text 单条 / url 抓正文 / markdown 按 --- 批量。"""
    if db is None:
        raise HTTPException(503, "Database not configured")

    content = body.content.strip()
    if not content:
        raise HTTPException(422, "内容不能为空")

    engine = body.engine if body.engine in {"codex", "claude", "cursor-agent"} else None
    resume = resume_text(4000)

    if body.mode == "url":
        raw_text = await _fetch_url_text(content)
        job_id = await _ingest_manual_text(
            raw_text=raw_text, source_url=content, engine=engine, resume=resume, db=db,
        )
        invalidate_scraped_cache()
        return {"id": job_id, "ids": [job_id], "ok": 1, "failed": []}

    if body.mode == "text":
        job_id = await _ingest_manual_text(
            raw_text=content, source_url="", engine=engine, resume=resume, db=db,
        )
        invalidate_scraped_cache()
        return {"id": job_id, "ids": [job_id], "ok": 1, "failed": []}

    if body.mode == "markdown":
        chunks = manual_job.split_markdown_jobs(content)
        if not chunks:
            raise HTTPException(422, "Markdown 里没有可用职位块。用单独一行的 --- 分隔多条。")
        if len(chunks) > manual_job.MAX_MARKDOWN_JOBS:
            raise HTTPException(
                422,
                f"一次最多 {manual_job.MAX_MARKDOWN_JOBS} 条，当前 {len(chunks)} 条，拆文件再传。",
            )
        ids: list[int] = []
        failed: list[dict] = []
        for i, chunk in enumerate(chunks, start=1):
            try:
                job_id = await _ingest_manual_text(
                    raw_text=chunk, source_url="", engine=engine, resume=resume, db=db,
                )
                ids.append(job_id)
            except HTTPException as e:
                detail = e.detail if isinstance(e.detail, str) else str(e.detail)
                failed.append({"index": i, "error": detail})
            except Exception as e:
                logger.exception("markdown job %s failed", i)
                failed.append({"index": i, "error": str(e)[:200]})
        invalidate_scraped_cache()
        if not ids:
            raise HTTPException(422, f"全部失败：{failed[0]['error'] if failed else '未知错误'}")
        return {
            "id": ids[0],
            "ids": ids,
            "ok": len(ids),
            "failed": failed,
            "total": len(chunks),
        }

    raise HTTPException(422, "mode 只能是 text / url / markdown")
