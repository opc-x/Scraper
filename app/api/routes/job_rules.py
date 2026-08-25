"""系统硬规则 CRUD —— 表 job_rules，读路径见 app.core.job_rules。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import job_rules as job_rules_lib
from app.db.connection import get_db
from app.db.schema import JobRule

router = APIRouter(prefix="/api/job-rules", tags=["job-rules"])

CATEGORIES = {
    "match_config",
    "match_stack",
    "match_signal",
    "match_cap",
    "match_verdict",
    "quality_block",
    "quality_suspect",
    "recall",
    "ingest_gate",
    "ingest_gate_config",
}


class JobRuleIn(BaseModel):
    category: str
    key: str
    label: str = ""
    pattern: str = ""
    weight: int = 0
    severity: str = ""
    enabled: bool = True
    rationale: str = ""
    config: dict = {}
    sort_order: int = 0


class JobRulePatch(BaseModel):
    label: str | None = None
    pattern: str | None = None
    weight: int | None = None
    severity: str | None = None
    enabled: bool | None = None
    rationale: str | None = None
    config: dict | None = None
    sort_order: int | None = None


def _row(r: JobRule) -> dict:
    return {
        "id": r.id,
        "category": r.category,
        "key": r.key,
        "label": r.label,
        "pattern": r.pattern,
        "weight": r.weight,
        "severity": r.severity,
        "enabled": r.enabled,
        "rationale": r.rationale,
        "config": r.config if isinstance(r.config, dict) else {},
        "sort_order": r.sort_order,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _validate(category: str, key: str, pattern: str, severity: str) -> None:
    if category not in CATEGORIES:
        raise HTTPException(400, f"category 必须是 {', '.join(sorted(CATEGORIES))}")
    if not key.strip():
        raise HTTPException(400, "key 不能为空")
    if pattern.strip():
        try:
            re.compile(pattern)
        except re.error as e:
            raise HTTPException(400, f"正则不合法：{e}")
    if severity and severity not in {"block", "suspect"}:
        raise HTTPException(400, "severity 只能是 block / suspect / 空")


@router.get("")
def list_rules(category: str = "", enabled: bool | None = None, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    job_rules_lib.seed_job_rules(db)
    q = db.query(JobRule)
    if category:
        q = q.filter_by(category=category)
    if enabled is not None:
        q = q.filter_by(enabled=enabled)
    rows = q.order_by(JobRule.category, JobRule.sort_order, JobRule.id).all()
    return {
        "rules": [_row(r) for r in rows],
        "categories": sorted(CATEGORIES),
        "total": len(rows),
    }


@router.post("")
def create_rule(body: JobRuleIn, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    _validate(body.category, body.key, body.pattern, body.severity)
    exists = db.query(JobRule).filter_by(category=body.category, key=body.key.strip()).first()
    if exists:
        raise HTTPException(409, f"已存在 {body.category}/{body.key}")
    row = JobRule(
        category=body.category,
        key=body.key.strip()[:64],
        label=(body.label or body.key).strip()[:128],
        pattern=body.pattern.strip()[:1024],
        weight=int(body.weight),
        severity=(body.severity or "").strip()[:16],
        enabled=bool(body.enabled),
        rationale=(body.rationale or "").strip(),
        config=body.config if isinstance(body.config, dict) else {},
        sort_order=int(body.sort_order),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    job_rules_lib.invalidate_cache()
    return _row(row)


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: JobRulePatch, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.get(JobRule, rule_id)
    if not row:
        raise HTTPException(404, "规则不存在")
    pattern = body.pattern if body.pattern is not None else row.pattern
    severity = body.severity if body.severity is not None else row.severity
    _validate(row.category, row.key, pattern or "", severity or "")
    if body.label is not None:
        row.label = body.label.strip()[:128]
    if body.pattern is not None:
        row.pattern = body.pattern.strip()[:1024]
    if body.weight is not None:
        row.weight = int(body.weight)
    if body.severity is not None:
        row.severity = body.severity.strip()[:16]
    if body.enabled is not None:
        row.enabled = bool(body.enabled)
    if body.rationale is not None:
        row.rationale = body.rationale.strip()
    if body.config is not None:
        row.config = body.config if isinstance(body.config, dict) else {}
    if body.sort_order is not None:
        row.sort_order = int(body.sort_order)
    db.commit()
    db.refresh(row)
    job_rules_lib.invalidate_cache()
    return _row(row)


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    if db is None:
        raise HTTPException(503, "Database not configured")
    row = db.get(JobRule, rule_id)
    if not row:
        raise HTTPException(404, "规则不存在")
    db.delete(row)
    db.commit()
    job_rules_lib.invalidate_cache()
    return {"ok": True}
