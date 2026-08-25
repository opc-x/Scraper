"""职位文本质量检查 —— 规则一律读 job_rules（quality_block / quality_suspect）。

高置信 block → data_quality_ok=False；suspect 只写报告不删不藏。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import job_rules


@dataclass(frozen=True)
class QualityFinding:
    kind: str
    severity: str
    reason: str
    evidence: str


def inspect_text(*, title: str = "", description: str = "") -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    title = title or ""
    description = description or ""
    desc = description.strip()
    hay = f"{title} {description}"

    for r in job_rules.by_category("quality_block"):
        cfg = r.config or {}
        if r.key == "incomplete":
            min_len = int(cfg.get("min_desc_len") or r.weight or 40)
            if (cfg.get("require_title", True) and not title.strip()) or len(desc) < min_len:
                findings.append(QualityFinding(
                    r.key, r.severity or "block", r.label or "信息不完整",
                    (title or desc)[:120],
                ))
            continue
        field = cfg.get("field", "hay")
        text = title if field == "title" else hay
        if r.pattern and r.pattern.search(text or ""):
            findings.append(QualityFinding(
                r.key, r.severity or "block", r.label or r.key, (title or desc)[:120],
            ))

    for r in job_rules.by_category("quality_suspect"):
        cfg = r.config or {}
        if r.key == "thin":
            lo = int(cfg.get("min_desc_len") or 40)
            hi = int(cfg.get("max_desc_len") or r.weight or 80)
            if desc and lo <= len(desc) < hi:
                findings.append(QualityFinding(
                    r.key, r.severity or "suspect", r.label or "正文偏短", desc[:120],
                ))
            continue
        if not r.pattern:
            continue
        hits = r.pattern.findall(desc)
        min_hits = int(cfg.get("min_hits") or 1)
        max_desc = cfg.get("max_desc_len")
        if len(hits) >= min_hits and (max_desc is None or len(desc) < int(max_desc)):
            evidence = (
                f"links={len(hits)}" if r.key == "link_heap"
                else ", ".join(dict.fromkeys(str(h) if not isinstance(h, tuple) else h[0] for h in hits))[:120]
            )
            # 已有同 kind 的 block 就不再叠 suspect
            if any(f.kind == r.key and f.severity == "block" for f in findings):
                continue
            findings.append(QualityFinding(
                r.key, r.severity or "suspect", r.label or r.key, evidence,
            ))

    return findings


def should_block(findings: list[QualityFinding]) -> bool:
    return any(f.severity == "block" for f in findings)
