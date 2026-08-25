"""简历画像 —— 匹配打分和职位评估都以这个为基准。

正文来自 docs/resumes/consolidated_2026.md，这里只做摘要和硬性口径，
避免每次给模型灌整份简历（贵且噪音大）。
"""

from __future__ import annotations

from pathlib import Path
import re

from app.core.salary import parse as parse_salary

RESUME_PATH = Path("docs/resumes/consolidated_2026.md")
ACTIVE_RESUME_PATH = Path("data/resumes/active.md")

# 打分口径写死在这儿，改口径就改这一处
PROFILE = """求职者画像：
- 定位：Java 后端负责人 / 技术专家，13 年经验（2013 至今）
- 履历：阿里巴巴 → 滴滴出行 → 火币科技 → JH科技，带过 5-20 人团队
- 核心技术栈：Java、多线程、JVM、Spring、Redis、MySQL、Kafka、Elasticsearch
- 大数据栈：Hadoop、Spark、Hive、Flink、Storm、数据仓库、数据中台、数据治理
- 擅长领域：分布式系统、高并发架构、元数据/数据血缘、调度系统、搜索引擎（ES + 排序算法）
- 行业经验：云计算、大数据平台、区块链钱包（Web3）、游戏后台、舆情分析
- 语言：中文母语，英文读写可以，口语一般
- 所在地：中国大陆，只能远程"""

HARD_RULES = """硬性口径：
1. 候选池仅允许三类：同时命中 Java 与远程；或命中 AI Agent；或 Node.js/Python 岗明确允许 AI 编程、专业门槛较低且年薪至少 12 万美元
2. 匹配度必须结合完整履历独立计算，禁止整批输出相同分数；Java 后端、分布式、大数据平台、高并发、技术负责人经历是主要加分项
3. 纯前端、纯设计、纯产品、销售市场、运维值班、硬件/嵌入式、非技术岗一律 0-20 分
4. 职责、资历、技术栈、行业、远程地域限制、英语要求和信息完整度都必须影响分数
5. 要求 onsite、本地工作许可、security clearance、必须某国公民的，最高 49 分
6. 聚合帖、职位合集、缺原始链接、描述不足以确认岗位的，最高 20 分"""

# 用户真正关心的工作偏好。标签必须有职位文本或薪资证据，禁止凭空夸公司。
PREFERENCE_RULES = (
    ("java", "Java", 18, r"\b(java|jvm|spring(?:\s*boot)?)\b"),
    ("agent", "Agent", 18, r"\b(ai agent|agentic|langgraph|langchain|crewai|autogen|multi[- ]agent|mcp)\b|智能体"),
    ("remote", "远程", 18, r"\b(remote|worldwide|anywhere|work from home|wfh)\b|远程"),
    ("few_meetings", "少开会", 12, r"\b(async[- ]first|meeting[- ]free|no meetings?|few meetings?|minimal meetings?)\b|少开会|无会议"),
    ("not_intense", "不卷", 12, r"\b(work[- ]life balance|no crunch|sustainable pace|four[- ]day|4[- ]day)\b|不加班|不内卷|工作生活平衡"),
    ("values", "价值观正", 22, r"\b(ethical|integrity|mission[- ]driven|social impact|values[- ]driven|transparent culture|do the right thing)\b|诚信|社会价值|使命驱动|做正确的事|价值观驱动"),
    ("rule_based", "非人治", 22, r"\b(rule[- ]based|policy[- ]driven|process[- ]driven|transparent decisions?|documented decisions?|objective criteria|clear accountability)\b|规则治理|制度治理|透明决策|客观标准|权责清晰|非人治"),
    ("non_bureaucratic", "不官僚", 22, r"\b(no bureaucracy|low bureaucracy|non[- ]bureaucratic|flat hierarchy|few layers|low politics|no office politics|low ego|direct communication)\b|不官僚|扁平管理|层级少|无办公室政治|直接沟通"),
    ("culture", "文化好", 10, r"\b(supportive|inclusive|collaborative|psychological safety|kind team|respectful)\b|包容|互相支持|尊重员工|团队友好"),
    ("atmosphere", "氛围好", 8, r"\b(friendly team|low ego|no blame|blameless|team camaraderie)\b|氛围好|扁平友好|无责备"),
    ("freedom", "自由度高", 12, r"\b(flexible hours?|flexible schedule|work whenever|autonomy|self[- ]directed|results[- ]only)\b|弹性工作|时间自由|自主安排"),
    ("low_workload", "事少", 10, r"\b(part[- ]time|32[- ]hour|four[- ]day|4[- ]day|reduced hours?)\b|兼职|四天工作制|工作量少"),
    ("humane", "人性化", 8, r"\b(unlimited pto|generous pto|parental leave|wellness|mental health|family[- ]friendly)\b|带薪休假|家庭友好|人性化"),
    ("structured", "制度化", 22, r"\b(well[- ]documented|mature process|clear process|structured onboarding|established team|documented process|written policy|clear governance)\b|流程规范|制度完善|文档完善|书面制度|治理清晰"),
)

PROJECT_MATCH = re.compile(
    r"\b(kafka|elasticsearch|hadoop|spark|hive|flink|storm|data platform|data warehouse|"
    r"data governance|metadata|data lineage|distributed systems?|high concurrency|web3|wallet|game backend)\b|"
    r"大数据|数据平台|数据中台|数据治理|元数据|数据血缘|分布式|高并发|钱包|游戏后台",
    re.I,
)


def preference_tags(*, title: str = "", description: str = "", salary: str = "",
                    city: str = "", skills: list | None = None) -> list[dict]:
    """从岗位原文提取贴身偏好标签；match 表示该偏好命中的可信度。"""
    text = " ".join([title or "", description or "", city or "", " ".join(skills or [])])
    tags = []
    for key, label, weight, pattern in PREFERENCE_RULES:
        match = re.search(pattern, text, re.I)
        if match:
            tags.append({"key": key, "label": label, "match": 100, "weight": weight,
                         "evidence": match.group(0)[:80]})
    salary_source = salary or text
    lo, hi = parse_salary(salary_source)
    if hi >= 150_000:
        tags.append({"key": "high_salary", "label": "高薪", "match": 100, "weight": 18,
                     "evidence": (salary or "职位描述中的薪资")[:80]})
    project = PROJECT_MATCH.search(text)
    if project:
        tags.append({"key": "project_match", "label": "项目贴合", "match": 90, "weight": 16,
                     "evidence": project.group(0)[:80]})
    keys = {tag["key"] for tag in tags}
    if "java" in keys and "project_match" in keys:
        tags.append({"key": "easy_start", "label": "上手快", "match": 85, "weight": 10,
                     "evidence": "Java + 既有项目经验"})
    if "high_salary" in keys and ({"low_workload", "few_meetings", "freedom"} & keys):
        tags.append({"key": "ideal_value", "label": "事少钱多", "match": 85, "weight": 20,
                     "evidence": "高薪 + 低负担/高自由度"})
    return sorted(tags, key=lambda item: (-item["weight"], item["label"]))


def resume_text(max_chars: int = 6000) -> str:
    """需要完整简历时才读文件（比如生成职位画像的深度评估）。"""
    if ACTIVE_RESUME_PATH.exists():
        text = ACTIVE_RESUME_PATH.read_text(encoding="utf-8").strip()
        if text:
            return text[:max_chars]
    if RESUME_PATH.exists():
        return RESUME_PATH.read_text(encoding="utf-8")[:max_chars]
    return PROFILE
