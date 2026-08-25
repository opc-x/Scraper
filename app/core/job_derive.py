"""职位衍生字段与自动标签的唯一计算入口 —— 写时算好落库，读接口只读列。

TECH_TAGS / REGIONS 这两套规则以前散落在 app/api/routes/scraped.py 里，现在挪到这，
因为 persist.py（写路径）和 scraped.py（读路径，兼容旧数据兜底时）都要用同一份定义。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.core import job_rules
from app.core import salary as salary_lib
from app.core.quality_inspect import inspect_text, should_block
from app.core.resume import preference_tags
from app.core.value_tags import ValueTag, low_english_ok, score_job_with
from app.ingest.contract import lang_for

TECH_TAGS = {
    "java": re.compile(r"(?<![a-zA-Z])java(?![a-zA-Z])", re.I),
    "nodejs": re.compile(r"\b(node(?:\.js|js)?|nestjs)\b", re.I),
    "python": re.compile(r"\b(python|django|fastapi)\b", re.I),
    "agent": re.compile(r"\b(ai agent|agents?|agentic|langchain|crewai)\b", re.I),
    "golang": re.compile(r"\b(go|golang)\b", re.I),
    "rust": re.compile(r"\brust\b", re.I),
    "llm": re.compile(r"\b(llm|large language model|rag)\b", re.I),
}
REGIONS = {
    "US": re.compile(r"\b(US|USA|United States|NYC|San Francisco|California)\b"),
    "EU": re.compile(r"\b(EU|Europe|European Union)\b"),
    "UK": re.compile(r"\b(UK|United Kingdom|London)\b"),
    "Canada": re.compile(r"\bCanada\b"),
    "APAC": re.compile(r"\b(APAC|Asia|India|Singapore|Australia)\b"),
}
REMOTE_RE = re.compile(
    r"remote|worldwide|anywhere|wfh|远程|居家|удал[её]н|remoto|teletrabajo|télétravail",
    re.I,
)
# 明确把中国大陆远程排除：必须人在某地、工作许可、onsite/hybrid、美国/英国 lock
CHINA_BLOCKED_RE = re.compile(
    r"\b(must be (?:located|based) in|only (?:in|for)|authorized to work in|"
    r"work authorization|us citizen|security clearance|eligible to work in|"
    r"no (?:visa )?sponsorship|onsite only|hybrid)\b",
    re.I,
)
_US_PLACE_RE = re.compile(
    r"\b(united states|\busa\b|u\.s\.a\.?|\bus\b|nyc|chicago|seattle|austin|"
    r"denver|boston|dallas|atlanta|portland|california|san francisco|"
    r"los angeles|new york|maryland|virginia|florida|texas|oregon)\b",
    re.I,
)
_WORLDWIDE_OK_RE = re.compile(
    r"worldwide|anywhere|non[- ]us|outside the us|no geo(?:graphic)? restrict",
    re.I,
)


def china_eligible(*, is_remote: bool, description: str = "", city: str = "") -> bool:
    """远程且描述没强制人在境外/工作许可/到岗，才算中国大陆可居家应聘。"""
    if not is_remote:
        return False
    blob = f"{city} {description}"
    if CHINA_BLOCKED_RE.search(blob):
        return False
    if re.search(r",\s*[A-Z]{2}\s*$", (city or "").strip()) and not _WORLDWIDE_OK_RE.search(blob):
        return False
    if _US_PLACE_RE.search(blob) and not _WORLDWIDE_OK_RE.search(blob):
        return False
    return True


_WFH_ANY_RE = re.compile(
    r"远程办公|居家办公|接受居家|全职远程|全远程|(?<!面试)远程(?!面试)|"
    r"fully\s*remote|work from home|\bwfh\b|\bremote(?:ly)?\b|\bworldwide\b|\banywhere\b|"
    r"удал[её]нн\w*|\bremoto\b|\bteletrabajo\b|\btélétravail\b",
    re.I,
)
_ONSITE_RE = re.compile(
    r"不支持远程|不接受居家|现场办公|全职现场|只要.{0,8}本地|每周.{0,8}现场|"
    r"base\s+[\u4e00-\u9fff]+|坐班|到岗办公",
    re.I,
)
_JAVA_PIVOT_RE = re.compile(r"转\s*go|转向\s*go|愿意转(?:向)?\s*go", re.I)
_JAVASCRIPT_RE = re.compile(r"\bjava\s*script\b", re.I)
_STACK_LIST_RE = re.compile(
    r"\b(java|python|javascript|typescript|golang|kotlin|flutter|vue|react|php|ruby|swift)\b",
    re.I,
)
_JAVA_NEAR_ROLE_RE = re.compile(
    r"(?<![a-zA-Z])java(?![a-zA-Z]).{0,48}"
    r"(engineer|developer|programmer|backend|开发|工程师|разработчик)"
    r"|(engineer|developer|programmer|backend|开发|工程师|разработчик).{0,48}"
    r"(?<![a-zA-Z])java(?![a-zA-Z])",
    re.I,
)
_GEO_LOCK_RE = re.compile(r"日本|日语\s*n[1-2]|马来西亚", re.I)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_INTERVIEW_REMOTE_RE = re.compile(r"远程面试|remote interviews?", re.I)
LENS_DAYS = 90


def _lens_lang(channel: str) -> str:
    return lang_for(channel)


_JAVA_TITLE_RE = TECH_TAGS["java"]  # job_rules 里 ingest_gate/java 没配 pattern 时的兜底


def java_in_title(title: str) -> bool:
    """入库硬条件：标题里出现独立的 java 一词。JavaScript 不算，转 Go 不算。

    正则不写死——读 job_rules ingest_gate/java 这条自己的 pattern，改这条规则的
    pattern 就能把「方向」换成 nodejs/python 之类，不用改代码；没配 pattern 时
    才用 _JAVA_TITLE_RE 兜底，保证空库也能跑。
    """
    text = title or ""
    if _JAVA_PIVOT_RE.search(text):
        return False
    rule = job_rules.rule_by_key("ingest_gate", "java")
    direction_re = getattr(rule, "pattern", None) if rule else None
    direction_re = direction_re or _JAVA_TITLE_RE
    if not direction_re.search(text):
        return False
    stacks = {m.group(1).lower() for m in _STACK_LIST_RE.finditer(text)}
    if len(stacks) >= 3:
        return False
    return True


def java_in_title_or_skills(
    title: str, skills: list[str] | None = None, *, description: str = "",
    city: str = "", channel: str = "",
) -> bool:
    """入库方向命中：标题、正文、城市或结构化技能里出现独立的 Java 均算命中。"""
    if java_in_title(title):
        return True
    blob = "\n".join([
        title or "", description or "", city or "",
        *(str(s or "") for s in (skills or [])),
    ])
    if _JAVA_PIVOT_RE.search(blob):
        return False
    rule = job_rules.rule_by_key("ingest_gate", "java")
    direction_re = getattr(rule, "pattern", None) if rule else None
    direction_re = direction_re or _JAVA_TITLE_RE
    description_without_js = _JAVASCRIPT_RE.sub(" ", description or "")
    hay = "\n".join([description_without_js, city or ""])
    if direction_re.search(hay):
        return True
    if (channel or "").strip().lower() != "remoteok":
        return False
    if not any(direction_re.search(str(skill or "")) for skill in (skills or [])):
        return False
    title_stacks = {m.group(1).lower() for m in _STACK_LIST_RE.finditer(title or "")}
    return not title_stacks


def _is_java_role(
    title: str, description: str, skills: list | None = None, *, mode: str = "both",
) -> bool:
    del mode
    return java_in_title_or_skills(title, skills, description=description)


def _is_wfh(
    title: str, description: str, city: str, *, mode: str = "both", channel: str = "",
) -> bool:
    del mode
    city_s = (city or "").strip()
    if "未知" in city_s or city_s.lower() in {"unknown", "n/a"}:
        city_s = ""
    blob = f"{city_s} {title} {description}"
    if _ONSITE_RE.search(blob):
        return False
    stripped = _INTERVIEW_REMOTE_RE.sub(" ", blob)
    city_s = (city or "").strip()
    generic_remote_city = bool(
        re.match(r"^(远程|remote|worldwide|anywhere|удал[её]нн\w*)$", city_s, re.I)
    )
    if generic_remote_city and "面试" not in title:
        return True
    ch = (channel or "").strip().lower()
    if ch in {"remoteok", "weworkremotely"}:
        if re.search(r"\bon[- ]?site only\b", stripped, re.I):
            return False
        return bool(_WFH_ANY_RE.search(stripped)) or generic_remote_city
    return bool(_WFH_ANY_RE.search(stripped))


def _posted_within_days(row, days: int = LENS_DAYS) -> bool:
    dt = getattr(row, "posted_at", None)
    if dt is None:
        return False
    if getattr(dt, "tzinfo", None):
        dt = dt.replace(tzinfo=None)
    return dt >= datetime.utcnow() - timedelta(days=days)


_GAP_META = {
    "java": (-11, "缺Java岗"),
    "remote": (-12, "缺远程"),
    "wfh": (-13, "缺居家"),
    "low_english": (-14, "缺低英语"),
    "fresh": (-15, "缺90天内"),
    "china": (-16, "缺大陆可投"),
}


class _SimplePosted:
    def __init__(self, posted_at):
        self.posted_at = posted_at


def _ingest_signals(
    *, title: str, description: str, city: str, is_remote: bool, skills: list[str],
    channel: str = "", posted_at=None,
) -> dict[str, bool]:
    # Java 扫标题、正文和结构化技能；其余条件串行扫完整 JD。
    del is_remote
    mode = _lens_lang(channel)
    jd = f"{city}\n{title}\n{description}"
    geo_locked = bool(_GEO_LOCK_RE.search(jd))
    wfh = _is_wfh(title, description, city, mode=mode, channel=channel)
    remote = bool(REMOTE_RE.search(jd)) and wfh
    ch = (channel or "").strip().lower()
    # x_zh 国内岗（杭州坐班等）本身就是大陆可投，不再绑「已经是远程」。
    china_as_remote = True if ch == "x_zh" else wfh
    return {
        "java": java_in_title_or_skills(
            title, skills, description=description, city=city, channel=channel,
        ),
        "remote": remote,
        "wfh": wfh,
        "low_english": low_english_ok(title, description, skills, mode=mode),
        "fresh": _posted_within_days(_SimplePosted(posted_at)),
        "china": (not geo_locked) and china_eligible(
            is_remote=china_as_remote, description=description, city=city,
        ),
    }


def matches_target_lens(row) -> bool:
    """Java 必中；其余入库条件加权 ≥ 系统规则阈值（默认 80%）即留。"""
    title = row.title or ""
    description = row.description or ""
    city = row.city or ""
    skills = getattr(row, "skills", None) or []
    is_remote = bool(REMOTE_RE.search(f"{city} {title} {description}"))
    passed, _detail = evaluate_ingest_gate(
        title=title, description=description, city=city, is_remote=is_remote,
        skills=skills if isinstance(skills, list) else [],
        channel=getattr(row, "channel", "") or "",
        posted_at=getattr(row, "posted_at", None),
        force=True,
    )
    return passed


def evaluate_ingest_gate(
    *, title: str, description: str, city: str, is_remote: bool, skills: list[str],
    channel: str = "", posted_at=None, force: bool = False,
) -> tuple[bool, dict]:
    """Java 必中。其余启用中的 ingest_gate 条件加权命中 ≥ 阈值才算过。

    总开关关闭时直接放行（force=True 时仍按 80% 拦，给 lens_only 入库用）。
    """
    threshold_row = job_rules.rule_by_key("ingest_gate_config", "threshold_pct")
    signals = _ingest_signals(
        title=title, description=description, city=city, is_remote=is_remote,
        skills=skills, channel=channel, posted_at=posted_at,
    )
    gate_off = not threshold_row or not getattr(threshold_row, "enabled", True)
    if gate_off and not force:
        return True, {"signals": signals, "ratio_pct": 100, "threshold_pct": 0}
    threshold_pct = threshold_row.weight if threshold_row else 80
    ch = (channel or "").strip().lower()
    if ch == "x_zh":
        override = job_rules.rule_by_key("ingest_gate_config", "threshold_pct_x_zh")
        threshold_pct = override.weight if override and getattr(override, "enabled", True) else 60
    conditions = [r for r in job_rules.by_category("ingest_gate") if getattr(r, "enabled", True)]
    if not conditions:
        if not force:
            return True, {"signals": signals, "ratio_pct": 100, "threshold_pct": 0}
        from types import SimpleNamespace as NS
        conditions = [
            NS(key=k, weight=25, enabled=True)
            for k in ("java", "remote", "wfh", "low_english", "fresh", "china")
        ]
    if not signals.get("java"):
        return False, {
            "signals": signals, "ratio_pct": 0, "threshold_pct": threshold_pct,
        }
    soft = [r for r in conditions if r.key != "java"]
    if not soft:
        return True, {
            "signals": signals, "ratio_pct": 100, "threshold_pct": threshold_pct,
        }
    total_weight = sum(r.weight for r in soft) or 1
    hit_weight = sum(r.weight for r in soft if signals.get(r.key))
    ratio_pct = round(hit_weight / total_weight * 100)
    return ratio_pct >= threshold_pct, {
        "signals": signals, "ratio_pct": ratio_pct, "threshold_pct": threshold_pct,
    }


def _gap_tags(signals: dict[str, bool]) -> list[dict]:
    tags = []
    for key, ok in signals.items():
        if ok:
            continue
        meta = _GAP_META.get(key)
        if not meta:
            continue
        tag_id, label = meta
        tags.append({
            "id": tag_id,
            "label": label,
            "polarity": -1,
            "weight": 0,
            "evidence": "入库口径未命中",
            "auto": True,
            "manual": False,
            "matched": True,
            "source": "ingest_gap",
        })
    return tags


def compute_derived(
    row, *, approved_tags: list[ValueTag], manual_ids: set[int],
) -> dict:
    """row 只要有 title/description/skills/city/salary/url 属性即可（ScrapedJob 实例）。
    approved_tags/manual_ids 由调用方批量加载好传进来，避免每条职位都查一次 DB。
    """
    skills = row.skills if isinstance(row.skills, list) else []
    title = row.title or ""
    description = row.description or ""
    city = row.city or ""
    salary = row.salary or ""
    haystack = " ".join([title, description, " ".join(skills)])

    # 两层自动标签在这里统一产出，所有 persist_scraped_jobs 入口共享：
    # core_tags 是事实/技术栈（列表无背景色），interest_tags 是重要特征（列表蓝色）。
    core_tags = [name for name, pattern in TECH_TAGS.items() if pattern.search(haystack)]
    regions = [name for name, pattern in REGIONS.items() if pattern.search(haystack)]
    is_remote = bool(REMOTE_RE.search(f"{city} {haystack}"))

    interest_tags = preference_tags(
        title=title, description=description, salary=salary, city=city, skills=skills,
    )
    preference_score = min(100, sum(tag["weight"] for tag in interest_tags))

    lo, hi = salary_lib.parse(salary)
    salary_cny = salary_lib.format_cny(lo, hi, salary_text=salary)[:64]

    findings = inspect_text(title=title, description=description)
    ok = not should_block(findings)

    mode = _lens_lang(getattr(row, "channel", "") or "")
    value_score, value_hits = score_job_with(
        approved_tags, manual_ids,
        title=title, description=description, city=city, skills=skills, salary=salary,
        low_english_mode=mode,
    )

    gate_passed, gate_detail = evaluate_ingest_gate(
        title=title, description=description, city=city, is_remote=is_remote, skills=skills,
        channel=getattr(row, "channel", "") or "",
        posted_at=getattr(row, "posted_at", None),
    )
    gap_tags = _gap_tags(gate_detail.get("signals") or {})
    seen_ids = {hit.get("id") for hit in value_hits if isinstance(hit, dict)}
    value_tags = [tag for tag in gap_tags if tag["id"] not in seen_ids] + list(value_hits)

    return {
        "core_tags": core_tags,
        "regions": regions,
        "is_remote": is_remote,
        "interest_tags": interest_tags,
        "preference_score": preference_score,
        "salary_min_usd": lo,
        "salary_max_usd": hi,
        "salary_bucket": salary_lib.bucket(hi),
        "salary_cny": salary_cny,
        "data_quality_ok": ok,
        "value_score": value_score,
        "value_tags": value_tags,
        "filtered_out": not gate_passed,
        "derived_at": datetime.utcnow(),
        "_quality_findings": [
            {"kind": f.kind, "severity": f.severity, "reason": f.reason, "evidence": f.evidence}
            for f in findings
        ],
    }


def apply_derived(row, *, approved_tags: list[ValueTag], manual_ids: set[int]) -> list[dict]:
    """算好直接 setattr 到 row 上，调用方负责 commit。
    返回质量发现（写 job_quality_reports 用），不落到 scraped_jobs 列。
    """
    derived = compute_derived(row, approved_tags=approved_tags, manual_ids=manual_ids)
    findings = derived.pop("_quality_findings", [])
    for key, value in derived.items():
        setattr(row, key, value)
    return findings


def recompute_value_scores(db, *, channel: str = "", external_id: str = "") -> int:
    """只重算 value_score/value_tags 这两列（其它衍生字段跟 value_tags 规则无关，不用动）。

    不传 channel/external_id 就是全量重算——value_tags 规则库改了之后用，这种改动很少发生，
    代价是一次性的，不影响读接口。传了就是单条重算——用户在详情页手动打/取消一个标签之后用。
    """
    from app.core import value_tags as value_tags_lib
    from app.db.schema import ScrapedJob

    approved_tags = value_tags_lib.list_approved(db)
    manual_map = value_tags_lib.load_manual_map(db)
    source_map = value_tags_lib.load_source_map(db)

    q = db.query(ScrapedJob)
    if channel and external_id:
        q = q.filter_by(channel=channel, external_id=external_id)
    rows = q.all()
    for row in rows:
        manual_ids = manual_map.get((row.channel, row.external_id), set())
        value_score, value_hits = score_job_with(
            approved_tags, manual_ids,
            title=row.title or "", description=row.description or "",
            city=row.city or "", skills=row.skills if isinstance(row.skills, list) else [],
            salary=row.salary or "",
            assignment_sources=source_map.get((row.channel, row.external_id), {}),
            low_english_mode=_lens_lang(row.channel or ""),
        )
        row.value_score = value_score
        row.value_tags = value_hits
        row.derived_at = datetime.utcnow()
    db.commit()
    value_tags_lib.invalidate_cache()
    return len(rows)
