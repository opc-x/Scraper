"""价值观标签的草稿生成 + 人工确认 CRUD。见 core/value_tags.py 的打分逻辑。"""

import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.routes.scraped import invalidate_scraped_cache
from app.core.job_derive import recompute_value_scores
from app.core.value_tag_draft import draft_fields, render_prompt
from app.core.value_tags import invalidate_cache
from app.db.connection import SessionLocal, get_db
from app.db.schema import ValueTag
from app.infra.local_ai import LocalAiError
from app.infra.local_ai import run as run_local_ai


def _recompute_all_in_background() -> None:
    """规则库变了，全量重算 value_score 落库；开新 session 是因为原请求的 session 这时已经关了。"""
    if not SessionLocal:
        return
    db = SessionLocal()
    try:
        recompute_value_scores(db)
    finally:
        db.close()

router = APIRouter(prefix="/api/value-tags", tags=["value-tags"])


class DraftRequest(BaseModel):
    description: str
    category: str = "价值观"
    polarity: int = 0


class TagFields(BaseModel):
    label: str
    pattern: str
    polarity: int
    weight: int


def _row_dict(t: ValueTag) -> dict:
    return {
        "id": t.id,
        "category": t.category,
        "description": t.description,
        "label": t.label,
        "pattern": t.pattern,
        "polarity": t.polarity,
        "weight": t.weight,
        "rationale": t.rationale,
        "status": t.status,
        "pinned": t.pinned,
        "created_at": t.created_at,
    }


def _validate_pattern(pattern: str) -> None:
    if not pattern:
        raise HTTPException(400, "正则不能为空")
    try:
        re.compile(pattern)
    except re.error as e:
        raise HTTPException(400, f"正则不合法：{e}")


@router.get("")
def list_tags(status: str = "", category: str = "", db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    q = db.query(ValueTag)
    if status:
        q = q.filter_by(status=status)
    if category:
        q = q.filter_by(category=category)
    rows = q.order_by(ValueTag.created_at.desc()).all()
    return {"tags": [_row_dict(r) for r in rows]}


@router.post("/draft")
async def draft_tag(req: DraftRequest, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    if not req.description.strip():
        raise HTTPException(400, "描述不能为空")
    try:
        data = await run_local_ai(render_prompt(req.description), engine="claude", timeout=90)
    except LocalAiError as exc:
        raise HTTPException(502, str(exc)) from exc
    fields = draft_fields(data)
    fields["polarity"] = req.polarity if req.polarity in {-1, 0, 1} else 0
    try:
        re.compile(fields["pattern"])
    except re.error:
        raise HTTPException(502, "模型生成的正则不合法，换个描述再试一次")

    tag = ValueTag(description=req.description.strip(), category=req.category.strip() or "价值观", status="draft", **fields)
    db.add(tag)
    db.commit()
    return _row_dict(tag)


@router.put("/{tag_id}")
def update_tag(
    tag_id: int, body: TagFields, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "标签不存在")
    _validate_pattern(body.pattern)
    tag.label = body.label.strip()[:64] or tag.label
    tag.pattern = body.pattern
    tag.polarity = body.polarity if body.polarity in {-1, 0, 1} else 0
    tag.weight = max(5, min(30, body.weight))
    db.commit()
    if tag.status == "approved":
        invalidate_cache()
        invalidate_scraped_cache()
        background_tasks.add_task(_recompute_all_in_background)
    return _row_dict(tag)


@router.post("/{tag_id}/approve")
def approve_tag(tag_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "标签不存在")
    _validate_pattern(tag.pattern)
    tag.status = "approved"
    db.commit()
    invalidate_cache()
    invalidate_scraped_cache()
    background_tasks.add_task(_recompute_all_in_background)
    return _row_dict(tag)


@router.post("/{tag_id}/unapprove")
def unapprove_tag(tag_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "标签不存在")
    tag.status = "draft"
    db.commit()
    invalidate_cache()
    invalidate_scraped_cache()
    background_tasks.add_task(_recompute_all_in_background)
    return _row_dict(tag)


@router.post("/{tag_id}/pin")
def pin_tag(tag_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "标签不存在")
    tag.pinned = True
    db.commit()
    invalidate_cache()
    return _row_dict(tag)


@router.post("/{tag_id}/unpin")
def unpin_tag(tag_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "标签不存在")
    tag.pinned = False
    db.commit()
    invalidate_cache()
    return _row_dict(tag)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    tag = db.query(ValueTag).filter_by(id=tag_id).first()
    if not tag:
        raise HTTPException(404, "Not found")
    was_approved = tag.status == "approved"
    db.delete(tag)
    db.commit()
    invalidate_cache()
    invalidate_scraped_cache()
    if was_approved:
        background_tasks.add_task(_recompute_all_in_background)
    return {"ok": True}
