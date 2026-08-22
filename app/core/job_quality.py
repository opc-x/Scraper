"""职位召回与数据质量门禁。

只决定岗位是否值得进入候选池；最终匹配度仍由本机 Codex 结合简历计算。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

JAVA = re.compile(r"\b(java|spring(?:boot)?|jvm)\b", re.I)
AGENT = re.compile(
    r"\b(ai agent|agent engineer|agent developer|agentic|langchain|langgraph|"
    r"crewai|autogen|tool calling|multi[- ]agent|mcp)\b|智能体(?:开发|工程)", re.I,
)
REMOTE = re.compile(r"\b(remote|worldwide|anywhere|work from home|wfh)\b|远程", re.I)
HANGZHOU = re.compile(r"杭州|hangzhou", re.I)
FOREIGN_LANGUAGE = re.compile(
    r"\b(english[- ]speaking|english (?:is )?required|working (?:in|language).*english|"
    r"international team|global team|overseas team|cross[- ]border team|"
    r"japanese[- ]speaking|japanese (?:is )?required)\b|"
    r"英语(?:办公|工作|沟通|交流|环境|能力|流利)|英文(?:办公|工作|沟通|交流|环境|能力|流利)|"
    r"外语环境|国际化团队|海外团队|日语(?:办公|工作|沟通|能力)",
    re.I,
)
NON_JOB = re.compile(
    r"hey job seekers|roles? \(\d+ found|job roundup|weekly jobs|multiple openings|"
    r"hiring list|职位合集|岗位汇总",
    re.I,
)
INVALID_TITLE = re.compile(r"^\s*(?:https?://|www\.)|^\s*(?:software engineering|remote)\s*$", re.I)
WRONG_ROLE = re.compile(
    r"\b(front[- ]?end|react native|designer|product manager|sales|marketing|recruiter|"
    r"customer success|legal|counsel|account executive|devops|sre|qa|ios|android)\b",
    re.I,
)


@dataclass(frozen=True)
class QualityResult:
    eligible: bool
    route: str
    reasons: tuple[str, ...]


def data_quality(*, title: str = "", description: str = "") -> tuple[bool, tuple[str, ...]]:
    """只剔除确定不是单个真实职位的脏记录，不拿偏好规则删数据。"""
    reasons: list[str] = []
    if not title.strip() or len((description or "").strip()) < 40:
        reasons.append("职位信息不完整")
    if INVALID_TITLE.search(title or ""):
        reasons.append("职位标题无效或过于宽泛")
    if NON_JOB.search(f"{title} {description}"):
        reasons.append("聚合帖或职位合集")
    return not reasons, tuple(reasons)


def row_data_quality(row) -> tuple[bool, tuple[str, ...]]:
    return data_quality(title=row.title or "", description=row.description or "")


def evaluate_job(*, title: str = "", description: str = "", city: str = "",
                 skills: list | None = None, salary: str = "", url: str = "") -> QualityResult:
    haystack = " ".join([title or "", description or "", city or "", " ".join(skills or [])])
    valid, quality_reasons = data_quality(title=title, description=description)
    reasons: list[str] = list(quality_reasons)
    if not (url or "").strip():
        reasons.append("缺少原始链接")
    java = bool(JAVA.search(haystack))
    agent = bool(AGENT.search(haystack))
    location_ok = bool(REMOTE.search(haystack) or HANGZHOU.search(city or ""))
    language_ok = bool(FOREIGN_LANGUAGE.search(haystack))

    route = "java" if java else "agent" if agent else ""
    if not route:
        reasons.append("非 Java/Agent 编程方向")
    if not location_ok:
        reasons.append("非远程且现场不在杭州")
    if not language_ok:
        reasons.append("未明确外语工作环境")
    if WRONG_ROLE.search(title or "") and not agent:
        reasons.append("岗位方向不符")
    preference_reasons = [reason for reason in reasons if reason == "未命中召回规则"]
    hard_reasons = [reason for reason in reasons if reason not in preference_reasons]
    return QualityResult(valid and not hard_reasons and bool(route), route, tuple(reasons))


def evaluate_row(row) -> QualityResult:
    return evaluate_job(
        title=row.title or "", description=row.description or "", city=row.city or "",
        skills=row.skills if isinstance(row.skills, list) else [], salary=row.salary or "", url=row.url or "",
    )
