"""匹配分混合裁定 —— 规则主裁、模型辅裁；权重/正则/硬顶一律读 job_rules。"""

from __future__ import annotations

from dataclasses import dataclass

from app.core import job_rules


@dataclass(frozen=True)
class MatchBreakdown:
    score: int
    rule_score: int
    llm_score: int
    verdict: str
    caps: tuple[str, ...]
    evidence: tuple[str, ...]


def _hay(*, title: str, description: str, city: str, skills: list[str]) -> str:
    return " ".join([title or "", description or "", city or "", " ".join(skills)])


def rule_score(
    *,
    title: str = "",
    description: str = "",
    city: str = "",
    skills: list | None = None,
) -> tuple[int, tuple[str, ...]]:
    skills = skills or []
    hay = _hay(title=title, description=description, city=city, skills=skills)
    score = job_rules.config_value("baseline", 20)
    evidence: list[str] = []

    for r in job_rules.by_category("match_stack"):
        if not r.pattern:
            continue
        m = r.pattern.search(hay)
        if m:
            score += r.weight
            evidence.append(f"{r.key}:{m.group(0)[:40]}")

    for r in job_rules.by_category("match_signal"):
        if not r.pattern:
            continue
        apply_on = (r.config or {}).get("apply_on", "hay")
        if apply_on == "city":
            text = city or ""
        elif apply_on == "hay_or_city":
            text = f"{hay} {city}"
        else:
            text = hay
        m = r.pattern.search(text)
        if not m:
            continue
        if r.key == "direction_agent" and any(e.startswith("direction_java:") for e in evidence):
            continue
        if r.key == "direction_java" and any(e.startswith("direction_agent:") for e in evidence):
            continue
        score += r.weight
        evidence.append(f"{r.key}:{m.group(0)[:40]}")

    return max(0, min(100, score)), tuple(evidence)


def compose(
    llm_fit: int,
    *,
    title: str = "",
    description: str = "",
    city: str = "",
    skills: list | None = None,
    one_liner: str = "",
) -> MatchBreakdown:
    llm = max(0, min(100, int(llm_fit or 0)))
    rule, evidence = rule_score(
        title=title, description=description, city=city, skills=skills,
    )
    rw = job_rules.config_value("rule_weight_pct", 65) / 100
    lw = job_rules.config_value("llm_weight_pct", 35) / 100
    mixed = round(rw * rule + lw * llm)
    caps: list[str] = []
    skills = skills or []
    hay = _hay(title=title, description=description, city=city, skills=skills)

    agent_hit = False
    agent_rule = job_rules.rule_by_key("match_signal", "direction_agent") or job_rules.rule_by_key("recall", "agent")
    if agent_rule and agent_rule.pattern and agent_rule.pattern.search(hay):
        agent_hit = True

    for r in job_rules.by_category("match_cap"):
        cfg = r.config or {}
        if r.key == "wrong_role":
            if cfg.get("unless_agent") and agent_hit:
                continue
            field = cfg.get("field", "title")
            text = title if field == "title" else hay
            if r.pattern and r.pattern.search(text or ""):
                mixed = min(mixed, r.weight)
                caps.append(f"{r.label}{r.weight}")
        elif r.key == "non_remote_non_hz":
            # pattern 命中 = 有远程/杭州；invert 时「未命中」才封顶
            text = f"{hay} {city}"
            hit = bool(r.pattern and (r.pattern.search(text) or r.pattern.search(city or "")))
            if cfg.get("invert") and not hit:
                mixed = min(mixed, r.weight)
                caps.append(f"{r.label}{r.weight}")

    gap_th = job_rules.config_value("llm_gap_threshold", 40)
    pull = job_rules.config_value("llm_gap_pull_pct", 25) / 100
    gap = llm - rule
    if abs(gap) > gap_th:
        mixed = round(mixed - gap * pull)
        caps.append("模型偏离收束")

    mixed = max(0, min(100, mixed))
    verdicts = sorted(job_rules.by_category("match_verdict"), key=lambda x: -x.weight)
    verdict = next((v.label for v in verdicts if mixed >= v.weight), "不建议")
    _ = one_liner
    return MatchBreakdown(
        score=mixed,
        rule_score=rule,
        llm_score=llm,
        verdict=verdict,
        caps=tuple(caps),
        evidence=evidence,
    )
