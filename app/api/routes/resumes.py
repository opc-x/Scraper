"""个人求职 app：简历增删改查。上传进库后转成 .md，供本机模型读取。"""

from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.resume import RESUME_PATH
from app.core.resume_convert import ResumeConvertError, ext_of, title_from_name, to_markdown
from app.db.connection import get_db
from app.db.schema import Resume, ResumeAnalysis, ResumeSuggestion, ResumeVersion

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

RESUME_DIR = Path("data/resumes")
ACTIVE_PATH = RESUME_DIR / "active.md"


class ResumeIn(BaseModel):
    title: str = ""
    markdown: str | None = None
    final_markdown: str | None = None


class ResumeUpload(BaseModel):
    filename: str
    content_b64: str
    title: str = ""


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _row(item: Resume, *, body: bool = False, db: Session | None = None) -> dict:
    version_count = 0
    current_version = 0
    if db is not None:
        version_count = db.query(ResumeVersion).filter_by(resume_id=item.id).count()
        cur = (
            db.query(ResumeVersion)
            .filter_by(resume_id=item.id, is_current=True)
            .first()
        )
        current_version = cur.version if cur else 0
    data = {
        "id": item.id,
        "title": item.title,
        "source_name": item.source_name,
        "source_format": item.source_format,
        "is_active": item.is_active,
        "chars": len(item.markdown or ""),
        "final_chars": len(getattr(item, "final_markdown", "") or ""),
        "version_count": version_count,
        "current_version": current_version,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }
    if body:
        data["markdown"] = item.markdown or ""
        data["final_markdown"] = getattr(item, "final_markdown", "") or ""
    return data


def _write_files(item: Resume) -> None:
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    (RESUME_DIR / f"{item.id}.md").write_text(item.markdown or "", encoding="utf-8")
    final_path = RESUME_DIR / f"{item.id}.final.md"
    if item.final_markdown:
        final_path.write_text(item.final_markdown, encoding="utf-8")
    elif final_path.exists():
        final_path.unlink()
    if item.is_active:
        ACTIVE_PATH.write_text(item.final_markdown or item.markdown or "", encoding="utf-8")


def _clear_active_file() -> None:
    if ACTIVE_PATH.exists():
        ACTIVE_PATH.unlink()


def _activate(db: Session, item: Resume) -> None:
    db.query(Resume).filter(Resume.id != item.id, Resume.is_active.is_(True)).update(
        {"is_active": False}
    )
    item.is_active = True


def _seed_if_empty(db: Session) -> None:
    if db.query(Resume).count() > 0:
        return
    if not RESUME_PATH.exists():
        return
    text = RESUME_PATH.read_text(encoding="utf-8").strip()
    if not text:
        return
    item = Resume(
        title=title_from_name(RESUME_PATH.name),
        markdown=text,
        source_name=RESUME_PATH.name,
        source_format="md",
        is_active=True,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _write_files(item)


@router.get("")
def list_resumes(db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _seed_if_empty(db)
    rows = db.query(Resume).order_by(Resume.is_active.desc(), Resume.updated_at.desc()).all()
    return {"resumes": [_row(r, db=db) for r in rows], "total": len(rows)}


@router.get("/{resume_id}")
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    return _row(item, body=True, db=db)


@router.post("")
def create_resume(body: ResumeIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    title = (body.title or "").strip() or "未命名简历"
    item = Resume(
        title=title[:80],
        markdown=body.markdown or "",
        final_markdown=body.final_markdown or "",
        source_name="",
        source_format="md",
        is_active=db.query(Resume).count() == 0,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    _write_files(item)
    return _row(item, body=True, db=db)


@router.post("/upload")
def upload_resume(body: ResumeUpload, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    try:
        data = base64.b64decode(body.content_b64, validate=False)
        markdown = to_markdown(body.filename, data)
    except ResumeConvertError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, "文件读不出来") from exc
    title = (body.title or "").strip() or title_from_name(body.filename)
    fmt = ext_of(body.filename).lstrip(".") or "md"
    if fmt == "markdown":
        fmt = "md"
    if fmt == "docx":
        fmt = "word"
    item = Resume(
        title=title[:80],
        markdown=markdown,
        source_name=body.filename,
        source_format=fmt if fmt in {"pdf", "word", "md"} else "md",
        is_active=True,
    )
    db.add(item)
    _activate(db, item)
    db.commit()
    db.refresh(item)
    _write_files(item)
    return _row(item, body=True, db=db)


@router.post("/{resume_id}/original")
def replace_original(resume_id: int, body: ResumeUpload, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    try:
        data = base64.b64decode(body.content_b64, validate=False)
        markdown = to_markdown(body.filename, data)
    except ResumeConvertError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, "文件读不出来") from exc
    fmt = ext_of(body.filename).lstrip(".") or "md"
    if fmt == "markdown":
        fmt = "md"
    if fmt == "docx":
        fmt = "word"
    item.markdown = markdown
    item.source_name = body.filename
    item.source_format = fmt if fmt in {"pdf", "word", "md"} else "md"
    if (body.title or "").strip():
        item.title = body.title.strip()[:80]
    _activate(db, item)
    db.commit()
    db.refresh(item)
    _write_files(item)
    return _row(item, body=True, db=db)


@router.put("/{resume_id}")
def update_resume(resume_id: int, body: ResumeIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    if body.title.strip():
        item.title = body.title.strip()[:80]
    if body.markdown is not None:
        item.markdown = body.markdown
    if body.final_markdown is not None:
        item.final_markdown = body.final_markdown
    db.commit()
    db.refresh(item)
    _write_files(item)
    return _row(item, body=True, db=db)


@router.post("/{resume_id}/activate")
def activate_resume(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    _activate(db, item)
    db.commit()
    db.refresh(item)
    _write_files(item)
    return _row(item, db=db)


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    item = db.get(Resume, resume_id)
    if item is None:
        raise HTTPException(404, "简历不存在")
    was_active = item.is_active
    db.query(ResumeVersion).filter_by(resume_id=resume_id).delete()
    db.query(ResumeSuggestion).filter_by(resume_id=resume_id).delete()
    db.query(ResumeAnalysis).filter_by(resume_id=resume_id).delete()
    db.delete(item)
    db.commit()
    for name in (f"{resume_id}.md", f"{resume_id}.final.md"):
        disk = RESUME_DIR / name
        if disk.exists():
            disk.unlink()
    if was_active:
        nxt = db.query(Resume).order_by(Resume.updated_at.desc()).first()
        if nxt:
            _activate(db, nxt)
            db.commit()
            _write_files(nxt)
        else:
            _clear_active_file()
    return {"ok": True}
