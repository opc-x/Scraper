"""个人求职 app：描述需求 → AI 出 SOP → 人改到满意。一份方案只出一份报告。"""

from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.default_sop import DEFAULT_SOP_DESCRIPTION, DEFAULT_SOP_NAME
from app.core.resume_suggest import draft_report_title
from app.core.sop_draft import normalize_models, parse_plan, render_prompt, sop_title
from app.db.connection import get_db
from app.db.schema import ResumeAnalysis, ResumeSop
from app.infra.local_ai import LocalAiError
from app.infra.local_ai import run as run_local_ai

router = APIRouter(prefix="/api/sops", tags=["sops"])


class SopIn(BaseModel):
    name: str = ""
    description: str | None = None
    brief: str | None = None
    models: list[str] | None = None
    steps: list[dict] | None = None


class GenerateIn(BaseModel):
    brief: str
    models: list[str] = []
    resume_id: int | None = None
    purpose: str = "analyze"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _row(item: ResumeSop) -> dict:
    steps = item.steps if isinstance(item.steps, list) else []
    models = item.models if isinstance(getattr(item, "models", None), list) else []
    return {
        "id": item.id,
        "resume_id": getattr(item, "resume_id", None),
        "name": item.name,
        "description": getattr(item, "description", "") or "",
        "brief": getattr(item, "brief", "") or "",
        "models": models,
        "steps": steps,
        "purpose": getattr(item, "purpose", None) or "analyze",
        "status": getattr(item, "status", None) or "draft",
        "is_active": item.is_active,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def _activate(db: Session, item: ResumeSop) -> None:
    db.query(ResumeSop).filter(ResumeSop.id != item.id, ResumeSop.is_active.is_(True)).update(
        {"is_active": False}
    )
    item.is_active = True


def _seq_for(name: str) -> int | None:
    if not name.startswith("#"):
        return None
    head = name[1:].split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def _purpose(raw: str | None) -> str:
    return raw if raw in {"analyze", "optimize"} else "analyze"


def _next_seq(db: Session, resume_id: int | None, purpose: str) -> int:
    q = db.query(ResumeSop).filter(ResumeSop.purpose == purpose)
    if resume_id is not None:
        q = q.filter((ResumeSop.resume_id == resume_id) | (ResumeSop.resume_id.is_(None)))
    nums = [_seq_for(item.name or "") for item in q.all()]
    found = [n for n in nums if n]
    return (max(found) + 1) if found else 1


def _find_draft(db: Session, resume_id: int | None, purpose: str) -> ResumeSop | None:
    q = db.query(ResumeSop).filter(ResumeSop.status == "draft", ResumeSop.purpose == purpose)
    if resume_id is not None:
        hit = q.filter(ResumeSop.resume_id == resume_id).order_by(ResumeSop.id.desc()).first()
        if hit:
            return hit
    return q.order_by(ResumeSop.is_active.desc(), ResumeSop.id.desc()).first()


def _rename_legacy(db: Session) -> None:
    dirty = False
    used_ids = {
        item.sop_id
        for item in db.query(ResumeAnalysis).all()
        if item.sop_id
    }
    for item in db.query(ResumeSop).all():
        if item.name in {"三合一", "五步硬审"}:
            item.name = DEFAULT_SOP_NAME
            dirty = True
        if not (getattr(item, "description", "") or "").strip() and item.name == DEFAULT_SOP_NAME:
            item.description = DEFAULT_SOP_DESCRIPTION
            dirty = True
        status = getattr(item, "status", None) or "draft"
        if item.id in used_ids and status != "used":
            item.status = "used"
            dirty = True
        elif not getattr(item, "status", None):
            item.status = "used" if item.id in used_ids else "draft"
            dirty = True
        if not (getattr(item, "purpose", None) or "").strip():
            item.purpose = "analyze"
            dirty = True
    all_sops = db.query(ResumeSop).order_by(ResumeSop.id.asc()).all()
    for i, item in enumerate(all_sops, start=1):
        steps = item.steps if isinstance(item.steps, list) else []
        rest = ""
        if _seq_for(item.name or "") and " " in (item.name or ""):
            rest = item.name.split(" ", 1)[1].strip()
            rest = re.sub(r"^这套\s*SOP\s*", "", rest).strip()
        if not rest or rest.startswith("只审"):
            rest = sop_title(getattr(item, "brief", "") or "", getattr(item, "description", "") or "", steps)
        new_name = f"#{i} {rest[:12]}"
        if item.name != new_name:
            item.name = new_name
            dirty = True
    by_resume: dict[int, list[ResumeAnalysis]] = {}
    for item in db.query(ResumeAnalysis).order_by(ResumeAnalysis.id.asc()).all():
        if item.sop_name in {"三合一", "五步硬审", ""}:
            item.sop_name = DEFAULT_SOP_NAME
            dirty = True
        by_resume.setdefault(item.resume_id, []).append(item)
    for rows in by_resume.values():
        for i, item in enumerate(rows, start=1):
            if item.title.startswith("#") and "性别" not in item.title and "五步硬审" not in item.title:
                continue
            findings = item.findings if isinstance(item.findings, list) else []
            item.title = f"#{i} {draft_report_title(findings)}"
            dirty = True
    if dirty:
        db.commit()


@router.get("")
def list_sops(db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _rename_legacy(db)
    rows = (
        db.query(ResumeSop)
        .order_by(ResumeSop.id.desc())
        .all()
    )
    return {"sops": [_row(r) for r in rows], "total": len(rows)}


@router.get("/{sop_id}")
def get_sop(sop_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeSop, sop_id)
    if item is None:
        raise HTTPException(404, "SOP 不存在")
    return _row(item)


@router.post("/generate")
async def generate_sop(body: GenerateIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    brief = (body.brief or "").strip()
    if not brief:
        raise HTTPException(400, "先写你要怎么审")
    _rename_legacy(db)
    models = normalize_models(body.models)
    engine = next((m for m in models if m in {"codex", "claude"}), "claude")
    try:
        data = await run_local_ai(render_prompt(brief, models), engine=engine, timeout=90)
    except LocalAiError as exc:
        raise HTTPException(502, str(exc)) from exc
    plan = parse_plan(data, brief=brief, models=models)
    purpose = _purpose(body.purpose)
    item = _find_draft(db, body.resume_id, purpose)
    if item is None or item.status == "used":
        item = ResumeSop(name=DEFAULT_SOP_NAME, purpose=purpose, is_active=True)
        db.add(item)
        db.flush()
        seq = _next_seq(db, body.resume_id, purpose)
    else:
        seq = _seq_for(item.name or "") or _next_seq(db, body.resume_id, purpose)
    item.resume_id = body.resume_id
    item.purpose = purpose
    item.name = f"#{seq} {plan['title']}"
    item.brief = brief[:2000]
    item.models = models
    item.description = plan["description"]
    item.steps = plan["steps"]
    item.status = "draft"
    _activate(db, item)
    db.commit()
    db.refresh(item)
    return _row(item)


@router.post("")
def create_sop(body: SopIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    name = (body.name or "").strip() or "SOP"
    item = ResumeSop(
        name=name[:80],
        description=(body.description or "").strip()[:200],
        brief=(body.brief or "").strip()[:2000],
        models=normalize_models(body.models),
        steps=body.steps or [],
        status="draft",
        is_active=True,
    )
    db.add(item)
    db.flush()
    _activate(db, item)
    db.commit()
    db.refresh(item)
    return _row(item)


@router.put("/{sop_id}")
def update_sop(sop_id: int, body: SopIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeSop, sop_id)
    if item is None:
        raise HTTPException(404, "SOP 不存在")
    if (getattr(item, "status", None) or "draft") == "used":
        raise HTTPException(400, "这份已经出过报告，改需求再生成一份")
    if body.name.strip():
        item.name = body.name.strip()[:80]
    if body.description is not None:
        item.description = body.description.strip()[:200]
    if body.brief is not None:
        item.brief = body.brief.strip()[:2000]
    if body.models is not None:
        item.models = normalize_models(body.models)
    if body.steps is not None:
        item.steps = body.steps
    db.commit()
    db.refresh(item)
    return _row(item)


@router.post("/{sop_id}/activate")
def activate_sop(sop_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeSop, sop_id)
    if item is None:
        raise HTTPException(404, "SOP 不存在")
    _activate(db, item)
    db.commit()
    db.refresh(item)
    return _row(item)


@router.delete("/{sop_id}")
def delete_sop(sop_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeSop, sop_id)
    if item is None:
        raise HTTPException(404, "SOP 不存在")
    was_active = item.is_active
    db.delete(item)
    db.commit()
    if was_active:
        nxt = (
            db.query(ResumeSop)
            .filter(ResumeSop.status == "draft")
            .order_by(ResumeSop.updated_at.desc())
            .first()
        )
        if nxt:
            _activate(db, nxt)
            db.commit()
    return {"ok": True}
