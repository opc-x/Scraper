"""价值观评分 —— 反 996 / 工作强度这条维度，用户可维护的标签库。

跟 core/resume.py 的 PREFERENCE_RULES（简历/技术栈贴合）是两回事：这套规则不写死
在代码里，用户拿大白话描述一个信号，本机 AI 转成正则草稿，人工确认后落库，
之后是纯正则匹配（不逐条调 LLM），才扛得住"默认给全量职位排序"这个用法。

一条职位的标签有两种来源：正则自动命中，或者用户在详情页手动打上（JobValueTag）。
两种来源打分权重一样，唯一区别是展示上标一下"手动"，别的地方平等对待。
"""

from __future__ import annotations

import re
import time
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.core import salary as salary_lib
from app.db.schema import JobValueTag, ValueTag

_cache: tuple[float, list[SimpleNamespace]] | None = None
_manual_cache: tuple[float, dict[tuple[str, str], set[int]]] | None = None
_source_cache: tuple[float, dict[tuple[str, str], dict[int, str]]] | None = None
_cache_ttl = 60

BASELINE = 50  # 没命中任何标签时的中性分

HIGH_ENGLISH_RE = re.compile(
    r"fluent(?:\s+in)?\s+english|native english|english (?:is )?required|"
    r"c1 english|c2 english|english c1|english c2|"
    r"professional (?:working )?english|excellent english|"
    r"must (?:be able to )?speak english",
    re.I,
)


def low_english_ok(
    title: str, description: str, skills: list[str] | None = None, *, mode: str = "both",
) -> bool:
    """没有 fluent/C1 这类高英语门槛就算过。正文可以是中文、英文、俄文，不要求中文办公。"""
    del mode
    text = " ".join([title or "", description or "", " ".join(skills or [])])
    return not HIGH_ENGLISH_RE.search(text)


def invalidate_cache() -> None:
    global _cache, _manual_cache, _source_cache
    _cache = None
    _manual_cache = None
    _source_cache = None


def list_approved(db: Session) -> list[SimpleNamespace]:
    return _load_approved(db)


def load_manual_map(db: Session) -> dict[tuple[str, str], set[int]]:
    return _load_manual_map(db)


def load_source_map(db: Session) -> dict[tuple[str, str], dict[int, str]]:
    global _source_cache
    if _source_cache and time.monotonic() - _source_cache[0] < _cache_ttl:
        return _source_cache[1]
    mapping: dict[tuple[str, str], dict[int, str]] = {}
    for channel, external_id, tag_id, source in db.query(
        JobValueTag.channel, JobValueTag.external_id, JobValueTag.tag_id, JobValueTag.source
    ):
        mapping.setdefault((channel, external_id), {})[tag_id] = source or "manual"
    _source_cache = (time.monotonic(), mapping)
    return mapping


def _freeze_tag(row: ValueTag) -> SimpleNamespace:
    # 缓存必须脱离 Session：commit 会 expire ORM 实例，下一请求再读 salary_below_usd 会 DetachedInstanceError。
    return SimpleNamespace(
        id=row.id,
        label=row.label,
        category=row.category,
        polarity=row.polarity,
        weight=row.weight,
        pattern=row.pattern,
        description=row.description,
        salary_below_usd=row.salary_below_usd,
        pinned=bool(row.pinned),
    )


def _load_approved(db: Session) -> list[SimpleNamespace]:
    global _cache
    if _cache and time.monotonic() - _cache[0] < _cache_ttl:
        return _cache[1]
    rows = [_freeze_tag(r) for r in db.query(ValueTag).filter_by(status="approved").all()]
    _cache = (time.monotonic(), rows)
    return rows


def _load_manual_map(db: Session) -> dict[tuple[str, str], set[int]]:
    global _manual_cache
    if _manual_cache and time.monotonic() - _manual_cache[0] < _cache_ttl:
        return _manual_cache[1]
    mapping: dict[tuple[str, str], set[int]] = {}
    for channel, external_id, tag_id in db.query(
        JobValueTag.channel, JobValueTag.external_id, JobValueTag.tag_id
    ):
        mapping.setdefault((channel, external_id), set()).add(tag_id)
    _manual_cache = (time.monotonic(), mapping)
    return mapping


def score_job(
    db: Session, *, channel: str = "", external_id: str = "",
    title: str, description: str, city: str, skills: list[str], salary: str = "",
) -> tuple[int, list[dict]]:
    """返回 (0-100 的价值观分, 标签明细)。没有任何已确认标签时退化成中性分 50。"""
    tags = _load_approved(db)
    manual_ids = _load_manual_map(db).get((channel, external_id), set())
    sources = load_source_map(db).get((channel, external_id), {})
    from app.core.job_derive import _lens_lang
    return score_job_with(
        tags, manual_ids, title=title, description=description,
        city=city, skills=skills, salary=salary, assignment_sources=sources,
        low_english_mode=_lens_lang(channel),
    )


def score_job_with(
    tags: list[ValueTag], manual_ids: set[int], *,
    title: str, description: str, city: str, skills: list[str], salary: str = "",
    assignment_sources: dict[int, str] | None = None,
    low_english_mode: str = "both",
) -> tuple[int, list[dict]]:
    """纯函数版本：调用方自己传已加载好的 approved tags + manual_ids，批量场景（写时预计算/
    规则变更后批量重算）用这个，省掉每条职位都查一次 DB。

    命中 = 正则自动匹配 / 薪资低于阈值（salary_below_usd 标签），或者这条职位被手动打上了
    这个标签（不管前两者命不命中）。

    负面标签（polarity=-1）仍保留未命中状态供详情页判断；列表页只展示 matched=True。
    正面（1）命中加分，负面（-1）命中减分，中性（0）只打标签、不改变分数。
    """
    # city 不进匹配文本：「远程」这类中文地点会把「低英语要求」整库误打成命中。
    text = " ".join([title or "", description or "", " ".join(skills or [])])
    _, salary_hi = salary_lib.parse(salary or "")
    hits: list[dict] = []
    score = BASELINE
    for tag in tags:
        if tag.salary_below_usd is not None:
            match = None
            auto_hit = salary_hi > 0 and salary_hi < tag.salary_below_usd
            evidence_text = f"披露年薪约 ${salary_hi:,} < ${tag.salary_below_usd:,}" if auto_hit else ""
        elif tag.label == "低英语要求":
            match = None
            auto_hit = low_english_ok(title, description, skills, mode=low_english_mode)
            evidence_text = "无高英语门槛" if auto_hit else ""
        else:
            try:
                match = re.search(tag.pattern, text, re.I)
            except re.error:
                match = None
            auto_hit = bool(match)
            evidence_text = match.group(0)[:80] if match else ""
        manual = tag.id in manual_ids
        matched = auto_hit or manual
        if matched:
            score += tag.weight * tag.polarity
        pinned = bool(getattr(tag, "pinned", False))
        if not matched and tag.polarity != -1 and not pinned:
            continue
        hits.append({
            "id": tag.id,
            "label": tag.label,
            "polarity": tag.polarity,
            "weight": tag.weight,
            "evidence": (evidence_text or "手动标注") if matched else "",
            "auto": auto_hit,
            "manual": manual,
            "source": "rule" if auto_hit else (assignment_sources or {}).get(tag.id, "manual"),
            "matched": matched,
        })
    return max(0, min(100, score)), hits


def set_manual_tag(
    db: Session, *, channel: str, external_id: str, tag_id: int, on: bool, source: str = "manual",
) -> None:
    existing = db.query(JobValueTag).filter_by(channel=channel, external_id=external_id, tag_id=tag_id).first()
    if on and not existing:
        db.add(JobValueTag(
            channel=channel, external_id=external_id, tag_id=tag_id,
            source=source if source in {"manual", "ai_assist", "ai_ingest"} else "manual",
        ))
        db.commit()
    elif not on and existing:
        db.delete(existing)
        db.commit()
    invalidate_cache()
