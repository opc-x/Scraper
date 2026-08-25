"""不依赖外部 AI：按简历硬规则完成评分，并为高分职位生成结构化画像。"""
from __future__ import annotations

import json
import re
from sqlalchemy import text
from app.db.connection import engine

JAVA = re.compile(r"\b(java|jvm|kotlin|scala)\b|spring(?:\s*boot)?", re.I)
DATA = re.compile(r"\b(hadoop|spark|hive|flink|storm|kafka|elasticsearch|data platform|data engineer|big data|distributed systems?)\b|大数据|分布式|数据平台|数据中台", re.I)
BACKEND = re.compile(r"\b(back[ -]?end|server[ -]?side|platform engineer|api engineer|microservices?)\b|后端|服务端|架构师", re.I)
LEAD = re.compile(r"\b(staff|principal|lead|architect|manager|senior)\b|负责人|技术专家", re.I)
OTHER_BACKEND = re.compile(r"\b(golang|go|rust|python|django|fastapi|node(?:\.js)?|nestjs)\b", re.I)
REMOTE = re.compile(r"\b(remote|worldwide|anywhere|distributed team)\b|远程", re.I)
RESTRICTED = re.compile(r"\b(onsite|on-site|security clearance|us citizens? only|must be (?:located|based|authorized)|work authorization required|no visa sponsorship)\b|必须到岗|仅限美国公民", re.I)
IRRELEVANT = re.compile(r"\b(front[ -]?end|react developer|vue developer|designer|product manager|sales|marketing|customer support|nurse|physician|mechanical|embedded|ios|android|qa engineer|devops|site reliability)\b|前端|设计师|产品经理|销售|市场|客服|医护|嵌入式|运维", re.I)


def score(row: dict) -> tuple[int, list[str], list[str]]:
    blob = " ".join(str(row.get(k) or "") for k in ("title", "description", "skills", "city"))
    matched: list[str] = []
    if IRRELEVANT.search(blob) and not (JAVA.search(blob) or DATA.search(blob) or BACKEND.search(blob)):
        value = 10
    elif JAVA.search(blob):
        value = 84; matched.append("Java / JVM 后端")
    elif DATA.search(blob):
        value = 82; matched.append("大数据 / 分布式系统")
    elif BACKEND.search(blob):
        value = 72; matched.append("后端 / 平台工程")
    elif OTHER_BACKEND.search(blob):
        value = 56; matched.append("跨语言后端经验可迁移")
    else:
        value = 32
    if LEAD.search(blob) and value >= 55:
        value += 6; matched.append("Senior / Staff / 负责人级别")
    if REMOTE.search(blob):
        value += 4; matched.append("远程")
    gaps: list[str] = []
    if RESTRICTED.search(blob):
        value //= 2; gaps.append("地域、身份或到岗限制")
    if re.search(r"\b(native|fluent) english\b|customer-facing|pre-sales", blob, re.I):
        value -= 8; gaps.append("英语口语或客户沟通要求")
    return max(0, min(96, value)), matched, gaps


def profile(row: dict, value: int, matched: list[str], gaps: list[str]) -> dict:
    if value >= 80: verdict = "强烈推荐"
    elif value >= 60: verdict = "值得一投"
    elif value >= 40: verdict = "谨慎"
    else: verdict = "不建议"
    restricted = bool(RESTRICTED.search(" ".join(str(row.get(k) or "") for k in ("title", "description", "city"))))
    return {
        "verdict": verdict, "fit_score": value,
        "one_liner": f"{verdict}：" + ("、".join(matched) if matched else "与 Java 后端负责人主线重合有限"),
        "salary_min_usd": 0, "salary_max_usd": 0, "salary_note": "需以招聘方原始薪资口径确认",
        "china_applicable": "有条件" if restricted else "可投",
        "china_reason": "存在地域、身份或到岗限制，投递前需确认" if restricted else "职位描述未发现明确排除中国大陆远程的条件",
        "stack_match": matched, "stack_gap": gaps, "seniority": "与 13 年经验及负责人/技术专家定位匹配" if value >= 70 else "需确认职级",
        "company_profile": "公开职位文本信息有限，建议面试时核实团队规模、业务阶段和汇报线",
        "red_flags": gaps, "apply_tips": ["突出 Java、高并发和分布式系统经历", "突出阿里、滴滴及团队管理经验", "投递前确认跨境远程与时区要求"],
        "info_quality": "一般" if len(row.get("description") or "") >= 200 else "信息太少",
        "generated_by": "resume-hard-rules-v1",
    }


def main() -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT id,channel,external_id,title,company,salary,city,skills,description,match_score
            FROM scraped_jobs WHERE match_score < 0 ORDER BY id
        """)).mappings().all()
    results = []
    for raw in rows:
        row = dict(raw)
        value, matched, gaps = score(row)
        results.append((row, value, matched, gaps))
    print(f"待完成 {len(results)} 条", flush=True)

    for start in range(0, len(results), 400):
        chunk = results[start:start + 400]
        cases = " ".join(f"WHEN {r['id']} THEN {value}" for r, value, _, _ in chunk)
        ids = ",".join(str(r["id"]) for r, _, _, _ in chunk)
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE scraped_jobs SET match_score=CASE id {cases} END WHERE id IN ({ids})"))
        print(f"评分 {min(start + 400, len(results))}/{len(results)}", flush=True)

    high = [item for item in results if item[1] >= 60]
    for start in range(0, len(high), 50):
        chunk = high[start:start + 50]
        params = {}; values = []
        for i, (row, value, matched, gaps) in enumerate(chunk):
            values.append(f"(:c{i},:e{i},:j{i},:v{i},:s{i},0,0,:p{i},'resume-hard-rules-v1')")
            params.update({f"c{i}":row["channel"], f"e{i}":row["external_id"], f"j{i}":row["id"],
                           f"v{i}":profile(row,value,matched,gaps)["verdict"], f"s{i}":value,
                           f"p{i}":json.dumps(profile(row,value,matched,gaps), ensure_ascii=False)})
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO job_profiles
              (channel,external_id,scraped_job_id,verdict,fit_score,salary_min,salary_max,profile,model)
              VALUES %s ON CONFLICT(channel,external_id) DO NOTHING""" % ",".join(values)), params)
        print(f"画像 {min(start + 50, len(high))}/{len(high)}", flush=True)
    print(f"完成：评分 {len(results)}，新建高分画像 {len(high)}", flush=True)


if __name__ == "__main__":
    main()
