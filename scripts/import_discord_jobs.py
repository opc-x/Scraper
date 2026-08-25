"""把浏览器采集的 Discord 招聘消息清洗后写入 scraped_jobs。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from app.core.job_origin import city_from_discord_text, origin_url
from app.db.connection import SessionLocal
from app.db.schema import Base, ScrapedJob

RAW_PATH = Path("data/discord_jobs_raw.jsonl")
TARGET_SKILLS = (
    ("Node.js", re.compile(r"\bnode(?:\.js)?\b", re.I)),
    ("Python", re.compile(r"\bpython\b", re.I)),
    ("Java", re.compile(r"\bjava\b", re.I)),
)
EXTRA_SKILLS = (
    ("Spring Boot", re.compile(r"\bspring boot\b", re.I)),
    ("React", re.compile(r"\breact(?:\.js)?\b", re.I)),
    ("TypeScript", re.compile(r"\btypescript\b", re.I)),
    ("JavaScript", re.compile(r"\bjavascript\b", re.I)),
    ("Django", re.compile(r"\bdjango\b", re.I)),
    ("FastAPI", re.compile(r"\bfastapi\b", re.I)),
    ("AWS", re.compile(r"\baws\b", re.I)),
)
SALARY_RE = re.compile(
    r"(?:[$€£¥]\s?\d[\d,.]*\s*(?:[KkMm])?(?:\s*[–—-]\s*[$€£¥]?\s?\d[\d,.]*\s*(?:[KkMm])?)?"
    r"(?:\s*(?:/\s*(?:hour|hr|year|yr|month|mo)|per\s+(?:hour|year|month)))?)"
)


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _dedupe_visible_title(line: str) -> str:
    """Discord 搜索结果会把线程标题渲染两遍，去掉紧邻的重复段。"""
    line = _collapse(line)
    for size in range(8, len(line) // 2 + 1):
        if line[:size] == line[size : size * 2]:
            return line[:size].strip()
    return line


def _title_company(text: str) -> tuple[str, str, str]:
    headline = _dedupe_visible_title(text.splitlines()[0])
    if " — " in headline:
        company, remainder = headline.split(" — ", 1)
    else:
        company, remainder = "未知", headline
    title = remainder.split(" | ", 1)[0].strip()
    return title[:256] or "Full-Stack Developer", company[:256] or "未知", headline


def _salary(text: str, headline: str) -> tuple[str, str]:
    match = SALARY_RE.search(headline) or SALARY_RE.search(text[:1600])
    if match:
        return _collapse(match.group(0))[:64], "明确薪资"
    if re.search(r"\b(unpaid|volunteer)\b|无薪", text, re.I):
        return "无薪", "无薪"
    if re.search(r"\b(negotiable|competitive|depending on experience|doe)\b", text, re.I):
        return "面议", "面议"
    return "未披露", "未披露"


def _city(text: str, headline: str) -> str:
    parsed = city_from_discord_text(text) or city_from_discord_text(headline)
    if parsed:
        return parsed
    if re.search(r"\bremote\b", headline, re.I):
        match = re.search(r"Remote(?:\s*[•·,-]\s*[^\n|]+)?", text, re.I)
        return _collapse(match.group(0))[:64] if match else "远程"
    match = re.search(r"(?:Location|地点)\s*[:：]\s*([^\n]{2,64})", text, re.I)
    return _collapse(match.group(1))[:64] if match else ""


def _skills(text: str) -> list[str]:
    return [name for name, pattern in (*TARGET_SKILLS, *EXTRA_SKILLS) if pattern.search(text)]


def _category(text: str) -> str | None:
    for name, pattern in TARGET_SKILLS:
        if pattern.search(text):
            return name
    return None


def load_jobs(path: Path, limit: int) -> list[dict]:
    # CronJobs 的 JobsBot 内容来自直接 ATS/RSS，排除社区自荐消息。
    by_category: dict[str, list[dict]] = defaultdict(list)
    seen_text: set[str] = set()
    seen_job: set[str] = set()

    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # 浏览器进程被 Discord 重载时可能留下半行，安全跳过。
            continue
        text = row.get("text", "")
        if row.get("server") != "CronJobs" or "JobsBot" not in text or text in seen_text:
            continue
        seen_text.add(text)
        category = _category(text)
        if not category:
            continue
        title, company, headline = _title_company(text)
        identity = _collapse(f"{company}|{title}").casefold()
        if identity in seen_job:
            continue
        seen_job.add(identity)
        salary, salary_tag = _salary(text, headline)
        external_id = "dc_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        captured_url = (row.get("url") or "")[:512]
        by_category[category].append(
            {
                "channel": "discord",
                "external_id": external_id,
                "title": title,
                "company": company,
                "salary": salary,
                "city": _city(text, headline),
                "experience": "",
                "education": "",
                "skills": _skills(text),
                "description": _collapse(text)[:12000],
                "url": origin_url(
                    "discord", external_id, captured_url, description=text,
                ),
                "raw": {
                    "salary_tag": salary_tag,
                    "source_server": row.get("server"),
                    "source_keyword": row.get("keyword"),
                    "captured_at": row.get("captured_at"),
                    "source_url": captured_url,
                },
            }
        )

    # 轮询三类技术栈，避免单一关键词把 500 条名额占满。
    selected: list[dict] = []
    categories = ["Node.js", "Python", "Java"]
    offsets = defaultdict(int)
    while len(selected) < limit:
        progressed = False
        for category in categories:
            index = offsets[category]
            if index < len(by_category[category]):
                selected.append(by_category[category][index])
                offsets[category] += 1
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
    return selected


def persist(jobs: list[dict]) -> tuple[int, int]:
    if SessionLocal is None:
        raise RuntimeError("数据库未配置")
    from app.db.connection import engine

    Base.metadata.create_all(engine, checkfirst=True)
    db = SessionLocal()
    inserted = 0
    updated = 0
    try:
        ids = [job["external_id"] for job in jobs]
        existing = {
            row.external_id: row
            for row in db.query(ScrapedJob).filter(ScrapedJob.external_id.in_(ids)).all()
        }
        for values in jobs:
            row = existing.get(values["external_id"])
            if row:
                for key, value in values.items():
                    setattr(row, key, value)
                updated += 1
            else:
                db.add(ScrapedJob(**values))
                inserted += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return inserted, updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=RAW_PATH)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    jobs = load_jobs(args.path, args.limit)
    counts = defaultdict(int)
    salary_tags = defaultdict(int)
    for job in jobs:
        primary = next(
            (skill for skill in ("Node.js", "Python", "Java") if skill in job["skills"]),
            "其他",
        )
        counts[primary] += 1
        salary_tags[job["raw"]["salary_tag"]] += 1
    summary = {"jobs": len(jobs), "stacks": dict(counts), "salary_tags": dict(salary_tags)}
    if args.dry_run:
        print(json.dumps(summary, ensure_ascii=False))
        return
    inserted, updated = persist(jobs)
    summary.update({"inserted": inserted, "updated": updated})
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
