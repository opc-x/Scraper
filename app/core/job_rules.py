"""统一职位规则库 —— 匹配分 / 质量门禁 / 召回信号都从 job_rules 读，禁止再散落写死。

价值观标签仍走 value_tags 表（用户可维护、要人工确认的那套）；
本表管「系统硬规则」：打分权重、栈证据、硬顶、垃圾文本判定。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_cache: tuple[float, list] | None = None
_cache_ttl = 30


@dataclass(frozen=True)
class CompiledRule:
    category: str
    key: str
    label: str
    pattern: re.Pattern[str] | None
    weight: int
    severity: str
    enabled: bool
    rationale: str
    config: dict
    sort_order: int


# 启动种子 / DB 不可用时的兜底，跟种子内容保持一致
SEED: list[dict] = [
    # —— 匹配混合权重 ——
    {"category": "match_config", "key": "rule_weight_pct", "label": "规则分占比", "weight": 65,
     "rationale": "终分里规则侧占比，剩下载给模型"},
    {"category": "match_config", "key": "llm_weight_pct", "label": "模型分占比", "weight": 35,
     "rationale": "终分里模型侧占比，故意压低防幻觉"},
    {"category": "match_config", "key": "baseline", "label": "规则分基数", "weight": 20,
     "rationale": "有正文但未命中栈时的起步分"},
    {"category": "match_config", "key": "llm_gap_threshold", "label": "模型偏离阈值", "weight": 40,
     "rationale": "模型分与规则分相差超过此值则向规则收束"},
    {"category": "match_config", "key": "llm_gap_pull_pct", "label": "偏离收束力度", "weight": 25,
     "rationale": "收束时按差距的百分比往规则拉（25=四分之一）"},
    # —— 栈证据加分 ——
    {"category": "match_stack", "key": "java", "label": "Java/JVM", "weight": 14,
     "pattern": r"\b(java|jvm|spring(?:\s*boot)?)\b"},
    {"category": "match_stack", "key": "kafka", "label": "Kafka", "weight": 8, "pattern": r"\bkafka\b"},
    {"category": "match_stack", "key": "elasticsearch", "label": "Elasticsearch", "weight": 8,
     "pattern": r"\b(elasticsearch|\bes\b)\b"},
    {"category": "match_stack", "key": "distributed", "label": "分布式/高并发", "weight": 8,
     "pattern": r"\b(distributed|高并发|分布式)\b"},
    {"category": "match_stack", "key": "bigdata", "label": "大数据栈", "weight": 8,
     "pattern": r"\b(hadoop|spark|hive|flink|storm|数据中台|数据平台)\b"},
    {"category": "match_stack", "key": "agent", "label": "AI Agent", "weight": 12,
     "pattern": r"\b(ai agent|agentic|langchain|langgraph|mcp|智能体)\b"},
    {"category": "match_stack", "key": "backend", "label": "后端", "weight": 6,
     "pattern": r"\b(backend|back[- ]end|服务端|后端)\b"},
    # —— 地点/方向信号 ——
    {"category": "match_signal", "key": "remote_or_hz", "label": "远程或杭州", "weight": 12,
     "pattern": r"\b(remote|worldwide|anywhere|work from home|wfh)\b|远程|杭州|hangzhou",
     "config": {"apply_on": "hay_or_city"}},
    {"category": "match_signal", "key": "direction_java", "label": "Java 方向", "weight": 8,
     "pattern": r"\b(java|spring(?:boot)?|jvm)\b"},
    {"category": "match_signal", "key": "direction_agent", "label": "Agent 方向", "weight": 8,
     "pattern": r"\b(ai agent|agent engineer|agentic|langchain|langgraph|mcp)\b|智能体"},
    # —— 硬顶 ——
    {"category": "match_cap", "key": "wrong_role", "label": "错岗封顶", "weight": 35,
     "pattern": (
         r"\b(front[- ]?end|react native|designer|product manager|sales|marketing|recruiter|"
         r"customer success|legal|counsel|account executive|devops|sre|qa|ios|android)\b"
     ),
     "config": {"unless_agent": True, "field": "title"},
     "rationale": "标题明显错岗且非 Agent 时最高分"},
    {"category": "match_cap", "key": "non_remote_non_hz", "label": "非远程非杭封顶", "weight": 49,
     "pattern": r"\b(remote|worldwide|anywhere|work from home|wfh)\b|远程|杭州|hangzhou",
     "config": {"invert": True, "apply_on": "hay_or_city"},
     "rationale": "没命中远程/杭州时最高 49"},
    # —— 分档文案 ——
    {"category": "match_verdict", "key": "strong", "label": "强烈推荐", "weight": 85, "sort_order": 1},
    {"category": "match_verdict", "key": "apply", "label": "值得一投", "weight": 65, "sort_order": 2},
    {"category": "match_verdict", "key": "caution", "label": "谨慎", "weight": 40, "sort_order": 3},
    {"category": "match_verdict", "key": "skip", "label": "不建议", "weight": 0, "sort_order": 4},
    # —— 质量：高置信 block ——
    {"category": "quality_block", "key": "incomplete", "label": "信息不完整", "weight": 40,
     "severity": "block", "config": {"min_desc_len": 40, "require_title": True},
     "rationale": "无标题或正文过短"},
    {"category": "quality_block", "key": "invalid_title", "label": "标题无效", "weight": 0,
     "severity": "block",
     "pattern": r"^\s*(?:https?://|www\.)|^\s*(?:software engineering|remote)\s*$",
     "config": {"field": "title"}},
    {"category": "quality_block", "key": "aggregate", "label": "聚合帖", "weight": 0,
     "severity": "block",
     "pattern": (
         r"hey job seekers|roles? \(\d+ found|job roundup|weekly jobs|multiple openings|"
         r"hiring list|职位合集|岗位汇总"
     )},
    # —— 质量：可疑只报案 ——
    {"category": "quality_suspect", "key": "thin", "label": "正文偏短", "weight": 80,
     "severity": "suspect", "config": {"min_desc_len": 40, "max_desc_len": 80},
     "rationale": "有正文但偏短，信息不一定够"},
    {"category": "quality_suspect", "key": "nav_noise", "label": "导航噪音", "weight": 2,
     "severity": "suspect",
     "pattern": (
         r"(cookie|privacy policy|terms of service|sign in|log in|订阅我们|下载 app|热门推荐|"
         r"相关职位|猜你喜欢|copyright\s*©|all rights reserved)"
     ),
     "config": {"min_hits": 2},
     "rationale": "命中导航/页脚词≥2 才报案，防误杀"},
    {"category": "quality_suspect", "key": "link_heap", "label": "链接堆", "weight": 8,
     "severity": "suspect", "pattern": r"https?://",
     "config": {"min_hits": 8, "max_desc_len": 500},
     "rationale": "短正文链接过多，疑似列表残渣"},
    # —— 召回（evaluate_job 用）——
    {"category": "recall", "key": "java", "label": "Java 召回", "weight": 0,
     "pattern": r"\b(java|spring(?:boot)?|jvm)\b"},
    {"category": "recall", "key": "agent", "label": "Agent 召回", "weight": 0,
     "pattern": (
         r"\b(ai agent|agent engineer|agent developer|agentic|langchain|langgraph|"
         r"crewai|autogen|tool calling|multi[- ]agent|mcp)\b|智能体(?:开发|工程)"
     )},
    {"category": "recall", "key": "remote", "label": "远程", "weight": 0,
     "pattern": r"\b(remote|worldwide|anywhere|work from home|wfh)\b|远程"},
    {"category": "recall", "key": "hangzhou", "label": "杭州", "weight": 0,
     "pattern": r"杭州|hangzhou", "config": {"field": "city"}},
    {"category": "recall", "key": "foreign_language", "label": "外语环境", "weight": 0,
     "pattern": (
         r"\b(english[- ]speaking|english (?:is )?required|working (?:in|language).*english|"
         r"international team|global team|overseas team|cross[- ]border team|"
         r"japanese[- ]speaking|japanese (?:is )?required)\b|"
         r"英语(?:办公|工作|沟通|交流|环境|能力|流利)|英文(?:办公|工作|沟通|交流|环境|能力|流利)|"
         r"外语环境|国际化团队|海外团队|日语(?:办公|工作|沟通|能力)"
     )},
    {"category": "recall", "key": "wrong_role", "label": "错岗", "weight": 0,
     "pattern": (
         r"\b(front[- ]?end|react native|designer|product manager|sales|marketing|recruiter|"
         r"customer success|legal|counsel|account executive|devops|sre|qa|ios|android)\b"
     ),
     "config": {"field": "title"}},
    # —— 入库门槛：落库前软过滤，未达标不删只标 filtered_out（见 job_derive.evaluate_ingest_gate）——
    {"category": "ingest_gate_config", "key": "threshold_pct", "label": "入库门槛",
     "weight": 80, "enabled": True,
     "rationale": "Java 必中；其余条件加权命中 ≥ 该百分比才入库。未命中的条件打「缺」标签"},
    {"category": "ingest_gate_config", "key": "threshold_pct_x_zh", "label": "X中文入库门槛",
     "weight": 60, "enabled": True,
     "rationale": "仅 x_zh：其余条件加权 ≥ 60% 即入库，比全局 80% 松"},
    {"category": "ingest_gate_config", "key": "rule_weight_pct", "label": "规则权重",
     "weight": 70, "enabled": True,
     "rationale": "scripts/rescue_ingest_gate.py 二次复核时，规则命中比例在最终分里的占比"},
    {"category": "ingest_gate_config", "key": "ai_weight_pct", "label": "AI 权重",
     "weight": 30, "enabled": True,
     "rationale": "AI 复议分在最终分里的占比；只用于捞回 Java 已命中但其余条件比例不够的职位"},
    {"category": "ingest_gate", "key": "java", "label": "Java 岗位", "weight": 25,
     "pattern": r"(?<![a-zA-Z])java(?![a-zA-Z])",
     "rationale": "硬条件：标题/正文/技能里命中独立 java 一词即可，不进比例；改 pattern 可换方向"},
    {"category": "ingest_gate", "key": "remote", "label": "远程", "weight": 25,
     "rationale": "复用 is_remote 派生列"},
    {"category": "ingest_gate", "key": "wfh", "label": "居家", "weight": 25,
     "rationale": "复用 job_derive._is_wfh，比「远程」更严格，排除仅远程面试这类噪音"},
    {"category": "ingest_gate", "key": "low_english", "label": "低英语要求", "weight": 25,
     "rationale": "复用价值观标签「低英语要求」命中，且排除「英语环境」命中"},
    {"category": "ingest_gate", "key": "fresh", "label": "90天内", "weight": 25,
     "rationale": "posted_at 在 90 天内"},
    {"category": "ingest_gate", "key": "china", "label": "大陆可投", "weight": 25,
     "rationale": "中国大陆可居家应聘"},
]


def invalidate_cache() -> None:
    global _cache
    _cache = None


def _compile_one(row: dict) -> CompiledRule | None:
    pattern_raw = (row.get("pattern") or "").strip()
    compiled = None
    if pattern_raw:
        try:
            compiled = re.compile(pattern_raw, re.I)
        except re.error:
            logger.warning("job_rules bad pattern %s/%s", row.get("category"), row.get("key"))
            return None
    cfg = row.get("config") if isinstance(row.get("config"), dict) else {}
    return CompiledRule(
        category=str(row["category"]),
        key=str(row["key"]),
        label=str(row.get("label") or row["key"]),
        pattern=compiled,
        weight=int(row.get("weight") or 0),
        severity=str(row.get("severity") or ""),
        enabled=bool(row.get("enabled", True)),
        rationale=str(row.get("rationale") or ""),
        config=cfg,
        sort_order=int(row.get("sort_order") or 0),
    )


def _from_seed() -> list[CompiledRule]:
    out: list[CompiledRule] = []
    for item in SEED:
        c = _compile_one({**item, "enabled": True})
        if c:
            out.append(c)
    return out


def _from_db(db: Session) -> list[CompiledRule]:
    from app.db.schema import JobRule

    rows = db.query(JobRule).filter_by(enabled=True).order_by(JobRule.sort_order, JobRule.id).all()
    out: list[CompiledRule] = []
    for r in rows:
        c = _compile_one({
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
        })
        if c:
            out.append(c)
    return out


def all_rules(*, force: bool = False) -> list[CompiledRule]:
    global _cache
    if not force and _cache and time.monotonic() - _cache[0] < _cache_ttl:
        return _cache[1]

    rules: list[CompiledRule] = []
    try:
        from app.db.connection import SessionLocal
        if SessionLocal:
            db = SessionLocal()
            try:
                rules = _from_db(db)
            finally:
                db.close()
    except Exception as e:
        logger.warning("job_rules load failed, fallback seed: %s", e)

    if not rules:
        rules = _from_seed()
    _cache = (time.monotonic(), rules)
    return rules


def by_category(category: str) -> list[CompiledRule]:
    return [r for r in all_rules() if r.category == category]


def config_value(key: str, default: int = 0) -> int:
    for r in by_category("match_config"):
        if r.key == key:
            return r.weight
    return default


def rule_by_key(category: str, key: str) -> CompiledRule | None:
    for r in by_category(category):
        if r.key == key:
            return r
    return None


def _migrate_ingest_threshold(db: Session) -> bool:
    """出厂 75% 入库门槛迁到 80% 并打开。人工改过权重的不碰。"""
    from app.db.schema import JobRule

    row = (
        db.query(JobRule)
        .filter_by(category="ingest_gate_config", key="threshold_pct")
        .first()
    )
    if not row or row.weight != 75:
        return False
    row.weight = 80
    row.enabled = True
    row.rationale = "Java 必中；其余条件加权命中 ≥ 80% 才入库"
    return True


def _migrate_ingest_java_pattern(db: Session) -> bool:
    """老库里 ingest_gate/java 这条没配 pattern（当时代码是硬写死的），
    现在改成读这条自己的 pattern 了，得把默认正则补进去，不然直接退化成兜底常量，
    等于用户在页面上改了这条也没用。已经手动配过 pattern 的不碰。
    """
    from app.db.schema import JobRule

    row = db.query(JobRule).filter_by(category="ingest_gate", key="java").first()
    if not row or row.pattern:
        return False
    row.pattern = r"(?<![a-zA-Z])java(?![a-zA-Z])"
    return True


def _migrate_ingest_java_scope(db: Session) -> bool:
    """标题-only 口径改成标题/正文/技能均可命中。人工改过且已含「正文」的不碰。"""
    from app.db.schema import JobRule

    row = db.query(JobRule).filter_by(category="ingest_gate", key="java").first()
    if not row:
        return False
    rationale = row.rationale or ""
    if "正文" in rationale:
        return False
    row.rationale = (
        "硬条件：标题/正文/技能里命中独立 java 一词即可，不进比例；改 pattern 可换方向"
    )
    return True


def seed_job_rules(db: Session | None = None) -> int:
    """按 (category, key) 补漏：已存在的键跳过（不覆盖人工改过的权重），
    只把 SEED 里新增的键插进去——这样新加的种子规则也能补到已经跑过一次的老库里。
    """
    from app.db.connection import SessionLocal
    from app.db.schema import JobRule

    own = False
    if db is None:
        if not SessionLocal:
            return 0
        db = SessionLocal()
        own = True
    try:
        existing = {(c, k) for c, k in db.query(JobRule.category, JobRule.key).all()}
        added = 0
        for item in SEED:
            if (item["category"], item["key"]) in existing:
                continue
            db.add(JobRule(
                category=item["category"],
                key=item["key"],
                label=item.get("label") or item["key"],
                pattern=item.get("pattern") or "",
                weight=int(item.get("weight") or 0),
                severity=item.get("severity") or "",
                enabled=item.get("enabled", True),
                rationale=item.get("rationale") or "",
                config=item.get("config") or {},
                sort_order=int(item.get("sort_order") or 0),
            ))
            added += 1
        migrated = _migrate_ingest_threshold(db)
        migrated = _migrate_ingest_java_pattern(db) or migrated
        migrated = _migrate_ingest_java_scope(db) or migrated
        if not added and not migrated:
            return 0
        db.commit()
        invalidate_cache()
        return added
    finally:
        if own:
            db.close()
