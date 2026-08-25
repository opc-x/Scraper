"""把质量检查结果写入 job_quality_reports，可溯源、可复跑。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.schema import JobQualityReport


def sync_reports(
    db: Session,
    *,
    channel: str,
    external_id: str,
    scraped_job_id: int | None,
    findings: list[dict],
    source: str = "rule",
) -> None:
    """按 (channel, external_id, kind) upsert；本轮没有的 kind 删掉，避免陈旧误报。"""
    existing = {
        r.kind: r
        for r in db.query(JobQualityReport).filter_by(channel=channel, external_id=external_id)
    }
    seen: set[str] = set()
    for item in findings:
        kind = str(item.get("kind") or "").strip()
        if not kind:
            continue
        seen.add(kind)
        row = existing.get(kind)
        if not row:
            row = JobQualityReport(channel=channel, external_id=external_id, kind=kind)
            db.add(row)
        row.scraped_job_id = scraped_job_id
        row.severity = str(item.get("severity") or "suspect")[:16]
        row.reason = str(item.get("reason") or "")[:256]
        row.evidence = str(item.get("evidence") or "")[:512]
        row.source = source
    for kind, row in existing.items():
        if kind not in seen:
            db.delete(row)
