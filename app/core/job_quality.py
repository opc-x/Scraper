"""职位召回与数据质量门禁 —— 召回正则从 job_rules.recall 读。

只决定岗位是否值得进入候选池；最终匹配度由 match_score 混合裁定。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import job_rules
from app.core.quality_inspect import inspect_text, should_block


@dataclass(frozen=True)
class QualityResult:
    eligible: bool
    route: str
    reasons: tuple[str, ...]


def _recall(key: str):
    return job_rules.rule_by_key("recall", key)


def data_quality(*, title: str = "", description: str = "") -> tuple[bool, tuple[str, ...]]:
    """高置信脏数据：与 quality_block 对齐。"""
    findings = inspect_text(title=title, description=description)
    blocked = [f for f in findings if f.severity == "block"]
    reasons = tuple(f.reason for f in blocked)
    return not blocked, reasons


def row_data_quality(row) -> tuple[bool, tuple[str, ...]]:
    return data_quality(title=row.title or "", description=row.description or "")


def evaluate_job(*, title: str = "", description: str = "", city: str = "",
                 skills: list | None = None, salary: str = "", url: str = "") -> QualityResult:
    haystack = " ".join([title or "", description or "", city or "", " ".join(skills or [])])
    valid, quality_reasons = data_quality(title=title, description=description)
    reasons: list[str] = list(quality_reasons)
    if not (url or "").strip():
        reasons.append("缺少原始链接")

    java_r = _recall("java")
    agent_r = _recall("agent")
    remote_r = _recall("remote")
    hz_r = _recall("hangzhou")
    lang_r = _recall("foreign_language")
    wrong_r = _recall("wrong_role")

    java = bool(java_r and java_r.pattern and java_r.pattern.search(haystack))
    agent = bool(agent_r and agent_r.pattern and agent_r.pattern.search(haystack))
    location_ok = bool(
        (remote_r and remote_r.pattern and remote_r.pattern.search(haystack))
        or (hz_r and hz_r.pattern and hz_r.pattern.search(city or ""))
    )
    language_ok = bool(lang_r and lang_r.pattern and lang_r.pattern.search(haystack))

    route = "java" if java else "agent" if agent else ""
    if not route:
        reasons.append("非 Java/Agent 编程方向")
    if not location_ok:
        reasons.append("非远程且现场不在杭州")
    if not language_ok:
        reasons.append("未明确外语工作环境")
    if wrong_r and wrong_r.pattern and wrong_r.pattern.search(title or "") and not agent:
        reasons.append("岗位方向不符")
    hard_reasons = reasons
    return QualityResult(valid and not hard_reasons and bool(route), route, tuple(reasons))


def evaluate_row(row) -> QualityResult:
    return evaluate_job(
        title=row.title or "", description=row.description or "", city=row.city or "",
        skills=row.skills if isinstance(row.skills, list) else [], salary=row.salary or "", url=row.url or "",
    )


# 兼容旧 import：测试/脚本若直接引 JAVA 等，改为函数属性懒加载
def __getattr__(name: str):
    mapping = {
        "JAVA": ("recall", "java"),
        "AGENT": ("recall", "agent"),
        "REMOTE": ("recall", "remote"),
        "HANGZHOU": ("recall", "hangzhou"),
        "FOREIGN_LANGUAGE": ("recall", "foreign_language"),
        "WRONG_ROLE": ("recall", "wrong_role"),
        "NON_JOB": ("quality_block", "aggregate"),
        "INVALID_TITLE": ("quality_block", "invalid_title"),
    }
    if name in mapping:
        cat, key = mapping[name]
        rule = job_rules.rule_by_key(cat, key)
        if rule and rule.pattern:
            return rule.pattern
        raise AttributeError(name)
    raise AttributeError(name)
