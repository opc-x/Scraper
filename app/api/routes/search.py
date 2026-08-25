from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapter
from app.api.routes.channels import SYNC_COVERAGE
from app.core.channel_config import CHANNEL_SCHEMA, load_config
from app.core.models import SearchRequest, SearchResponse
from app.core.sync_query import parse_and_derive
from app.db.connection import SessionLocal, get_db
from app.db.persist import persist_scraped_jobs
from app.db.schema import ChannelSyncPreset, ChannelSyncRun

router = APIRouter(prefix="/api", tags=["search"])


class ChannelSyncRequest(BaseModel):
    query: str = ""
    keyword: str = ""
    city: str = ""
    within_days: int = 90


class SyncPresetRequest(BaseModel):
    name: str
    query: str


def _preset_dict(preset: ChannelSyncPreset) -> dict:
    return {
        "id": preset.id,
        "channel": preset.channel,
        "name": preset.name,
        "query": preset.query,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }


@router.get("/channels/{channel}/sync-presets")
async def list_sync_presets(channel: str, db: Session = Depends(get_db)):
    rows = (
        db.query(ChannelSyncPreset)
        .filter_by(channel=channel)
        .order_by(ChannelSyncPreset.updated_at.desc(), ChannelSyncPreset.id.desc())
        .all()
    )
    return {"presets": [_preset_dict(row) for row in rows]}


@router.post("/channels/{channel}/sync-presets")
async def create_sync_preset(
    channel: str, body: SyncPresetRequest, db: Session = Depends(get_db)
):
    name, query = body.name.strip(), body.query.strip()
    if not name or not query:
        raise HTTPException(422, "名称和查询内容不能为空")
    parsed = await parse_and_derive(query)
    if not parsed["keyword_expr"]["terms"]:
        raise HTTPException(422, "查询缺少关键字")
    preset = ChannelSyncPreset(channel=channel, name=name[:64], query=query)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return {"preset": _preset_dict(preset)}


@router.put("/channels/{channel}/sync-presets/{preset_id}")
async def update_sync_preset(
    channel: str,
    preset_id: int,
    body: SyncPresetRequest,
    db: Session = Depends(get_db),
):
    preset = db.query(ChannelSyncPreset).filter_by(id=preset_id, channel=channel).first()
    if not preset:
        raise HTTPException(404, "查询预设不存在")
    name, query = body.name.strip(), body.query.strip()
    if not name or not query:
        raise HTTPException(422, "名称和查询内容不能为空")
    preset.name = name[:64]
    preset.query = query
    preset.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(preset)
    return {"preset": _preset_dict(preset)}


@router.delete("/channels/{channel}/sync-presets/{preset_id}")
async def delete_sync_preset(
    channel: str, preset_id: int, db: Session = Depends(get_db)
):
    preset = db.query(ChannelSyncPreset).filter_by(id=preset_id, channel=channel).first()
    if not preset:
        raise HTTPException(404, "查询预设不存在")
    db.delete(preset)
    db.commit()
    return {"ok": True}


def _run_dict(run: ChannelSyncRun) -> dict:
    return {
        "id": run.id,
        "channel": run.channel,
        "status": run.status,
        "pulled": run.pulled,
        "coverage": run.coverage,
        "query": run.query,
        "parsed_query": run.parsed_query or {},
        "error": run.error,
        "logs": run.logs or [],
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def _append_log(run: ChannelSyncRun, message: str) -> None:
    run.logs = [*(run.logs or []), {"at": datetime.utcnow().isoformat(), "message": message}]


def _empty_result_error(channel: str) -> str:
    if channel == "boss":
        return (
            "BOSS 没有返回任何职位。Cookie 很可能已过期，或页面触发了安全验证。"
            "请重新登录 zhipin.com、更新 Cookie，完成浏览器里的验证后再试。"
        )
    if channel == "telegram":
        return "Telegram 没有读取到招聘消息。请检查账号登录状态、监听来源和 DeepSeek Key。"
    if channel == "discord":
        return "Discord 没有读取到招聘消息。请检查 User Token、频道权限和监听来源。"
    if channel in {"x", "x_zh"}:
        return "X 没有返回招聘帖子。请检查浏览器登录状态（scripts/x_login.py）。"
    return "渠道连接成功，但没有找到可入库的数据。请检查渠道配置和数据源后重试。"


def _job_time(job) -> datetime | None:
    raw = job.raw or {}
    value = next((raw.get(key) for key in (
        "posted_at", "published_at", "published", "date", "created_at"
    ) if raw.get(key)), None)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _matches(job, parsed: dict) -> bool:
    blob = f"{job.title} {job.company} {' '.join(job.skills)} {job.description}".lower()
    location = f"{job.city} {blob}".lower()

    def match(expr: dict, haystack: str, derived: list[str]) -> bool:
        source = expr["terms"] if expr["op"] == "and" else (derived or expr["terms"])
        terms = [str(term).lower() for term in source]
        if not terms:
            return True
        hits = [term in haystack for term in terms]
        return all(hits) if expr["op"] == "and" else any(hits)

    return match(parsed["keyword_expr"], blob, parsed["derived_keywords"]) and match(
        parsed["location_expr"], location, parsed["derived_locations"]
    )


async def _collect_jobs(run: ChannelSyncRun, parsed: dict):
    adapter = get_adapter(run.channel)
    days = parsed["within_days"]
    if run.channel == "eleduck":
        jobs = await adapter.fetch_recent(max_age_days=days, min_jobs=1, fetch_details=False)
        coverage = f"已按发布时间扫描并截断近 {days} 天"
    else:
        keywords = parsed["derived_keywords"][:4]
        jobs_by_key = {}
        for keyword in keywords:
            max_pages = 10 if run.channel == "boss" else 1
            for page in range(1, max_pages + 1):
                batch = await adapter.search(SearchRequest(
                    keyword=keyword,
                    city="",
                    channel=run.channel,
                    page=page,
                    within_days=days,
                ))
                for job in batch:
                    jobs_by_key[(job.channel, job.external_id)] = job
                if not batch:
                    break
        jobs = list(jobs_by_key.values())
        coverage = {
            "boss": f"每个派生词最多扫描 10 页；BOSS 不提供可靠发布时间，未保证覆盖近 {days} 天",
            "telegram": f"已按消息时间滚动到近 {days} 天截止点",
            "discord": f"已按消息时间分页到近 {days} 天截止点",
            "x": f"仅扫描实时搜索首屏，未保证覆盖近 {days} 天（X 风控限制）",
            "x_zh": f"中文全站搜索并下翻，按 since: 截到近 {days} 天",
            "v2ex": f"仅扫描 Atom 最新 50 条，未保证覆盖近 {days} 天",
        }.get(run.channel, f"未保证覆盖近 {days} 天")
    cutoff = datetime.utcnow() - timedelta(days=days)
    filtered = [
        job
        for job in jobs
        if (_job_time(job) is None or _job_time(job) >= cutoff) and _matches(job, parsed)
    ]
    return filtered, coverage


async def _execute_sync(run_id: int) -> None:
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        run = db.get(ChannelSyncRun, run_id)
        if not run:
            return
        run.status = "running"
        run.started_at = datetime.utcnow()
        _append_log(run, "已连接渠道，开始读取最近数据")
        db.commit()

        cfg = load_config().get(run.channel, {})
        parsed = await parse_and_derive(run.query or run.keyword, cfg.get("llm_api_key", ""))
        run.parsed_query = parsed
        _append_log(run, f"查询解析：{parsed}")
        db.commit()
        jobs, coverage = await _collect_jobs(run, parsed)
        run.coverage = coverage
        if not jobs:
            raise RuntimeError(_empty_result_error(run.channel))
        _append_log(run, f"采集完成，共解析 {len(jobs)} 条，正在去重入库")
        db.commit()
        persist_scraped_jobs(jobs)

        run.status = "succeeded"
        run.pulled = len(jobs)
        run.finished_at = datetime.utcnow()
        _append_log(run, f"同步成功：处理 {len(jobs)} 条职位")
        db.commit()
    except Exception as exc:
        db.rollback()
        run = db.get(ChannelSyncRun, run_id)
        if run:
            run.status = "failed"
            run.error = str(exc)[:2000]
            run.finished_at = datetime.utcnow()
            _append_log(run, f"同步失败：{run.error}")
            db.commit()
    finally:
        db.close()


@router.get("/channels/{channel}/sync/latest")
async def latest_channel_sync(channel: str, db: Session = Depends(get_db)):
    run = (
        db.query(ChannelSyncRun)
        .filter(ChannelSyncRun.channel == channel)
        .order_by(ChannelSyncRun.id.desc())
        .first()
    )
    if run and run.status == "succeeded" and run.pulled == 0:
        run.status = "failed"
        run.error = _empty_result_error(channel)
        _append_log(run, f"结果修正为失败：{run.error}")
        db.commit()
    return {"run": _run_dict(run) if run else None}


@router.post("/channels/{channel}/sync")
async def sync_channel(
    channel: str,
    body: ChannelSyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    schema = CHANNEL_SCHEMA.get(channel)
    if not schema:
        raise HTTPException(404, f"Unknown channel: {channel}")
    if channel not in SYNC_COVERAGE:
        raise HTTPException(409, "该渠道尚未接入手动拉取")

    cfg = load_config().get(channel, {})
    if not cfg.get("enabled"):
        raise HTTPException(409, "请先启用并保存该渠道")
    missing = [
        field["label"]
        for field in schema["fields"]
        if field.get("required") and not cfg.get(field["key"])
    ]
    if missing:
        raise HTTPException(409, f"缺少配置：{'、'.join(missing)}")

    query = (body.query or cfg.get("sync_query") or "").strip()
    if not query and body.keyword:
        query = f"{body.keyword} | {body.city} | {body.within_days}"
    parsed = await parse_and_derive(query, cfg.get("llm_api_key", ""))
    if not parsed["keyword_expr"]["terms"]:
        raise HTTPException(422, "抓取查询缺少关键字，请按“关键字 | 地点 | 天数”填写")

    active = db.query(ChannelSyncRun).filter(
        ChannelSyncRun.channel == channel,
        ChannelSyncRun.status.in_(["queued", "running"]),
    ).order_by(ChannelSyncRun.id.desc()).first()
    if active:
        return {
            "run": _run_dict(active),
            "already_running": True,
            "pulled": active.pulled,
            "coverage": active.coverage,
        }

    run = ChannelSyncRun(
        channel=channel,
        status="queued",
        keyword=query[:128],
        city="",
        query=query,
        parsed_query=parsed,
        coverage=f"待执行：近 {parsed['within_days']} 天",
        logs=[
            {"at": datetime.utcnow().isoformat(), "message": "任务已创建，等待执行"},
            {"at": datetime.utcnow().isoformat(), "message": f"查询：{query}"},
        ],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_execute_sync, run.id)
    return {
        "run": _run_dict(run),
        "already_running": False,
        "pulled": 0,
        "coverage": run.coverage,
    }


@router.post("/search", response_model=SearchResponse)
async def search_jobs(req: SearchRequest):
    adapter = get_adapter(req.channel)
    jobs = await adapter.search(req)
    persist_scraped_jobs(jobs)
    return SearchResponse(
        jobs=jobs,
        total=len(jobs),
        page=req.page,
        channel=req.channel,
    )
