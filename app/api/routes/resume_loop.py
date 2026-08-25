"""原稿 → 建议 → 采纳 → 落版本。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.resumes import _write_files
from app.core.resume_suggest import draft_analysis, draft_report_title, draft_suggestions
from app.db.connection import get_db
from app.db.schema import Resume, ResumeAnalysis, ResumeSop, ResumeSuggestion, ResumeVersion

router = APIRouter(prefix="/api/resumes", tags=["resume-loop"])


class SuggestIn(BaseModel):
    model: str = "claude"
    models: list[str] = []
    sop_id: int | None = None
    analysis_id: int | None = None
    brief: str = ""
    direct: bool = False


class SuggestionStatusIn(BaseModel):
    status: str


class AnalysisTitleIn(BaseModel):
    title: str


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _need(db: Session, resume_id: int) -> Resume:
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    return item


def _version_row(item: ResumeVersion) -> dict:
    return {
        "id": item.id,
        "resume_id": item.resume_id,
        "version": item.version,
        "markdown": item.markdown or "",
        "note": item.note,
        "model": item.model,
        "is_current": item.is_current,
        "chars": len(item.markdown or ""),
        "created_at": _iso(item.created_at),
    }


def _analysis_row(item: ResumeAnalysis, *, body: bool = True) -> dict:
    findings = item.findings if isinstance(item.findings, list) else []
    data = {
        "id": item.id,
        "resume_id": item.resume_id,
        "sop_id": item.sop_id,
        "sop_name": item.sop_name,
        "title": item.title,
        "finding_count": len(findings),
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }
    if body:
        data["findings"] = findings
    return data


def _fold_legacy_analysis(db: Session, resume_id: int) -> None:
    if db.query(ResumeAnalysis).filter_by(resume_id=resume_id).count() > 0:
        return
    rows = (
        db.query(ResumeSuggestion)
        .filter_by(resume_id=resume_id, kind="analysis")
        .order_by(ResumeSuggestion.id.asc())
        .all()
    )
    if not rows:
        return
    db.add(
        ResumeAnalysis(
            resume_id=resume_id,
            sop_id=None,
            sop_name="",
            title=f"分析报告 · {len(rows)} 条",
            findings=[{"title": r.title, "quote": r.quote, "body": r.body} for r in rows],
        )
    )
    db.query(ResumeSuggestion).filter_by(resume_id=resume_id, kind="analysis").delete()
    db.commit()


def _suggestion_row(item: ResumeSuggestion) -> dict:
    return {
        "id": item.id,
        "resume_id": item.resume_id,
        "model": item.model,
        "title": item.title,
        "quote": item.quote,
        "body": item.body,
        "status": item.status,
        "kind": getattr(item, "kind", None) or "optimize",
        "created_at": _iso(item.created_at),
    }


def _current_text(db: Session, resume: Resume) -> str:
    cur = (
        db.query(ResumeVersion)
        .filter_by(resume_id=resume.id, is_current=True)
        .first()
    )
    if cur and cur.markdown:
        return cur.markdown
    return resume.markdown or ""


def _set_current_version(db: Session, resume: Resume, item: ResumeVersion) -> None:
    db.query(ResumeVersion).filter(
        ResumeVersion.resume_id == resume.id,
        ResumeVersion.id != item.id,
        ResumeVersion.is_current.is_(True),
    ).update({"is_current": False})
    item.is_current = True
    resume.final_markdown = item.markdown or ""


@router.get("/{resume_id}/versions")
def list_versions(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _need(db, resume_id)
    rows = (
        db.query(ResumeVersion)
        .filter_by(resume_id=resume_id)
        .order_by(ResumeVersion.version.desc())
        .all()
    )
    return {"versions": [_version_row(r) for r in rows], "total": len(rows)}


@router.get("/{resume_id}/versions/{version_id}")
def get_version(resume_id: int, version_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeVersion, version_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "版本不存在")
    return _version_row(item)


@router.post("/{resume_id}/versions/{version_id}/activate")
def activate_version(resume_id: int, version_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    resume = _need(db, resume_id)
    item = db.get(ResumeVersion, version_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "版本不存在")
    _set_current_version(db, resume, item)
    db.commit()
    db.refresh(item)
    _write_files(resume)
    return _version_row(item)


@router.delete("/{resume_id}/versions/{version_id}")
def delete_version(resume_id: int, version_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    resume = _need(db, resume_id)
    item = db.get(ResumeVersion, version_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "版本不存在")
    was_current = item.is_current
    db.delete(item)
    db.commit()
    if was_current:
        nxt = (
            db.query(ResumeVersion)
            .filter_by(resume_id=resume_id)
            .order_by(ResumeVersion.version.desc())
            .first()
        )
        if nxt:
            _set_current_version(db, resume, nxt)
        else:
            resume.final_markdown = ""
        db.commit()
        _write_files(resume)
    return {"ok": True}


@router.get("/{resume_id}/suggestions")
def list_suggestions(resume_id: int, kind: str | None = None, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _need(db, resume_id)
    q = db.query(ResumeSuggestion).filter_by(resume_id=resume_id)
    if kind in {"analysis", "optimize"}:
        q = q.filter_by(kind=kind)
    order = ResumeSuggestion.id.asc() if kind == "analysis" else ResumeSuggestion.id.desc()
    rows = q.order_by(order).all()
    return {"suggestions": [_suggestion_row(r) for r in rows], "total": len(rows)}


@router.get("/{resume_id}/analyses")
def list_analyses(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _need(db, resume_id)
    from app.api.routes.sops import _rename_legacy
    _rename_legacy(db)
    _fold_legacy_analysis(db, resume_id)
    rows = (
        db.query(ResumeAnalysis)
        .filter_by(resume_id=resume_id)
        .order_by(ResumeAnalysis.id.desc())
        .all()
    )
    return {"analyses": [_analysis_row(r, body=False) for r in rows], "total": len(rows)}


@router.get("/{resume_id}/analyses/{analysis_id}")
def get_analysis(resume_id: int, analysis_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeAnalysis, analysis_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "报告不存在")
    return _analysis_row(item)


@router.put("/{resume_id}/analyses/{analysis_id}")
def update_analysis(resume_id: int, analysis_id: int, body: AnalysisTitleIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeAnalysis, analysis_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "报告不存在")
    title = body.title.strip()[:80]
    if not title:
        raise HTTPException(400, "标题不能空")
    item.title = title
    db.commit()
    db.refresh(item)
    return _analysis_row(item)


@router.delete("/{resume_id}/analyses/{analysis_id}")
def delete_analysis(resume_id: int, analysis_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(ResumeAnalysis, analysis_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "报告不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/{resume_id}/analyze")
def analyze_resume(resume_id: int, body: SuggestIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    resume = _need(db, resume_id)
    if body.direct:
        brief = (body.brief or "").strip()
        if not brief:
            raise HTTPException(400, "先写你要怎么审")
        steps = [{"title": "按需求审", "quote": "", "body": brief}]
        findings = draft_analysis(resume.markdown or "", sop_steps=steps)
        seq = db.query(ResumeAnalysis).filter_by(resume_id=resume_id).count() + 1
        item = ResumeAnalysis(
            resume_id=resume_id,
            sop_id=None,
            sop_name="直接",
            title=f"#{seq} {draft_report_title(findings)}",
            findings=findings,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return _analysis_row(item)
    sop = None
    steps: list[dict] = []
    if body.sop_id:
        sop = db.get(ResumeSop, body.sop_id)
    if sop is None:
        sop = (
            db.query(ResumeSop)
            .filter(ResumeSop.status == "draft")
            .order_by(ResumeSop.is_active.desc(), ResumeSop.id.desc())
            .first()
        )
    if sop is None:
        raise HTTPException(400, "先生成一份 SOP")
    if (getattr(sop, "status", None) or "draft") == "used":
        raise HTTPException(400, "这份 SOP 已经出过报告，改需求再生成一份")
    taken = db.query(ResumeAnalysis).filter_by(sop_id=sop.id).first()
    if taken:
        raise HTTPException(400, "这份 SOP 已经出过报告，改需求再生成一份")
    if isinstance(sop.steps, list):
        steps = sop.steps
    if not steps:
        raise HTTPException(400, "SOP 还没有步骤，先改到有内容")
    findings = draft_analysis(resume.markdown or "", sop_steps=steps)
    seq = db.query(ResumeAnalysis).filter_by(resume_id=resume_id).count() + 1
    name = sop.name if sop else "SOP"
    item = ResumeAnalysis(
        resume_id=resume_id,
        sop_id=sop.id if sop else None,
        sop_name=name,
        title=f"#{seq} {draft_report_title(findings)}",
        findings=findings,
    )
    db.add(item)
    sop.status = "used"
    sop.is_active = False
    db.commit()
    db.refresh(item)
    return _analysis_row(item)


@router.post("/{resume_id}/suggest")
def create_suggestions(resume_id: int, body: SuggestIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    resume = _need(db, resume_id)
    model = body.model if body.model in {"claude", "codex", "cursor"} else "claude"
    brief = (body.brief or "").strip()
    findings: list[dict] = []
    if body.analysis_id:
        report = db.get(ResumeAnalysis, body.analysis_id)
        if report is None or report.resume_id != resume_id:
            raise HTTPException(404, "报告不存在")
        if isinstance(report.findings, list):
            findings = report.findings
    if not brief:
        raise HTTPException(400, "先写你要怎么改")
    if not findings:
        raise HTTPException(400, "先选一份分析报告")
    if body.sop_id:
        sop = db.get(ResumeSop, body.sop_id)
        if sop is None:
            raise HTTPException(404, "SOP 不存在")
        if (getattr(sop, "status", None) or "draft") == "used":
            raise HTTPException(400, "这份 SOP 已经用过，再出一张")
        extra = sop.steps if isinstance(sop.steps, list) else []
        findings = [
            {"title": str(s.get("title") or ""), "quote": "", "body": str(s.get("body") or "")}
            for s in extra
            if str(s.get("title") or "").strip()
        ] + findings
        sop.status = "used"
        sop.is_active = False
    db.query(ResumeSuggestion).filter_by(
        resume_id=resume_id, status="pending", kind="optimize"
    ).delete()
    text = _current_text(db, resume)
    for raw in draft_suggestions(text, model=model, findings=findings, brief=brief):
        db.add(
            ResumeSuggestion(
                resume_id=resume_id,
                model=model,
                title=raw["title"][:80],
                quote=raw.get("quote") or "",
                body=raw["body"],
                status="pending",
                kind="optimize",
            )
        )
    db.commit()
    rows = (
        db.query(ResumeSuggestion)
        .filter_by(resume_id=resume_id, kind="optimize")
        .order_by(ResumeSuggestion.id.desc())
        .all()
    )
    return {"suggestions": [_suggestion_row(r) for r in rows], "total": len(rows)}


@router.post("/{resume_id}/suggestions/{suggestion_id}")
def set_suggestion(resume_id: int, suggestion_id: int, body: SuggestionStatusIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    if body.status not in {"pending", "adopted", "rejected"}:
        raise HTTPException(400, "status 只能是 pending / adopted / rejected")
    item = db.get(ResumeSuggestion, suggestion_id)
    if item is None or item.resume_id != resume_id:
        raise HTTPException(404, "建议不存在")
    item.status = body.status
    db.commit()
    db.refresh(item)
    return _suggestion_row(item)


@router.post("/{resume_id}/apply")
def apply_suggestions(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    resume = _need(db, resume_id)
    adopted = (
        db.query(ResumeSuggestion)
        .filter_by(resume_id=resume_id, status="adopted", kind="optimize")
        .order_by(ResumeSuggestion.id.asc())
        .all()
    )
    if not adopted:
        raise HTTPException(400, "先采纳至少一条建议")
    base = _current_text(db, resume)
    last = (
        db.query(ResumeVersion)
        .filter_by(resume_id=resume_id)
        .order_by(ResumeVersion.version.desc())
        .first()
    )
    next_no = (last.version + 1) if last else 1
    note_lines = [f"- {s.title}：{s.body}" for s in adopted]
    markdown = base.rstrip() + "\n\n---\n\n## v{n} 采纳\n\n{body}\n".format(
        n=next_no,
        body="\n".join(note_lines),
    )
    item = ResumeVersion(
        resume_id=resume_id,
        version=next_no,
        markdown=markdown,
        note=f"采纳 {len(adopted)} 条 · {adopted[0].model}",
        model=adopted[0].model,
        is_current=True,
    )
    db.add(item)
    db.flush()
    _set_current_version(db, resume, item)
    db.query(ResumeSuggestion).filter_by(resume_id=resume_id, kind="optimize").delete()
    db.commit()
    db.refresh(item)
    _write_files(resume)
    return _version_row(item)
