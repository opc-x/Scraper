"""把 X 挖掘抓到的推文转成岗位，写入 scraped_jobs。

数据来自 data/x_mining_raw.json（mine_x_remote_hiring_bulk.py 抓的每个账号 20 条发帖），
账号标签来自 data/x_tagged_accounts.json。不按「中国可投」过滤 —— 先全量入库再筛。

用法：
    python -m scripts.import_x_jobs --min-confidence 50
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

RAW = Path("data/x_mining_raw.json")
TAGS = Path("data/x_tagged_accounts.json")
OUT = Path("data/x_jobs.json")

ROLE_RE = re.compile(
    r"\b(engineer|developer|programmer|architect|devops|sre|scientist|analyst|designer|"
    r"qa|tester|product manager|tech lead|cto|fullstack|full[- ]stack|backend|frontend)\b", re.I)
HIRING_RE = re.compile(
    r"\b(hiring|we[' ]?re hiring|now hiring|job|vacancy|position|opening|apply|role|"
    r"looking for|join (our|the) team|jobalert|remotejob)\b", re.I)
SEEKING_RE = re.compile(
    r"\b(open to work|looking for (a |an )?(job|work|role)|hire me|#forhire|"
    r"available for (hire|work)|my portfolio|i'?m looking for a)\b", re.I)
SALARY_RE = re.compile(
    r"[$€£]\s?\d[\d,.]*\s?[kK]?(?:\s?[-–—]\s?[$€£]?\s?\d[\d,.]*\s?[kK]?)?"
    r"(?:\s?(?:per|/)\s?(?:year|yr|month|mo|hour|hr|week))?")
REMOTE_RE = re.compile(r"\bremote\b|\bwork from anywhere\b|\bworldwide\b", re.I)
LOC_RE = re.compile(
    r"\b(worldwide|global|anywhere|US|USA|EU|Europe|UK|Canada|LATAM|APAC|Asia|"
    r"Germany|Poland|Portugal|Spain|India|Brazil|Nigeria|Kenya)\b")
URL_RE = re.compile(r"https?://[^\s]+")
SKILLS = [
    "Node.js", "Nodejs", "Node", "JavaScript", "TypeScript", "Python", "Django", "FastAPI",
    "Java", "Spring", "Kotlin", "Golang", "Go", "Rust", "C++", "C#", ".NET", "PHP", "Laravel",
    "Ruby", "Rails", "React", "Vue", "Angular", "Svelte", "Next.js", "AWS", "GCP", "Azure",
    "Kubernetes", "Docker", "Terraform", "PostgreSQL", "MySQL", "MongoDB", "Redis", "Kafka",
    "GraphQL", "LLM", "RAG", "LangChain", "AI agent", "Agent", "PyTorch", "TensorFlow", "Solidity",
]


def is_job(text: str) -> bool:
    if SEEKING_RE.search(text) and not HIRING_RE.search(text):
        return False
    return bool(ROLE_RE.search(text) and HIRING_RE.search(text))


# 招聘号最常见的句式：「<公司> is hiring (a remote candidate) for <岗位>」
COMPANY_RE = re.compile(r"^\s*([A-Z][\w .,&'\-]{1,50}?)\s+(?:is|are|we[' ]?re)\s+hiring\b", re.I | re.M)
ROLE_AFTER_RE = re.compile(r"hiring\s+(?:a\s+remote\s+candidate\s+)?(?:a |an )?for\s+(.+)", re.I)
ROLE_AFTER2_RE = re.compile(r"\bhiring\s+(?:a |an )?([A-Z][^\n|.!?]{5,80})", re.I)


def company_of(text: str) -> str:
    m = COMPANY_RE.search(text)
    if m:
        c = m.group(1).strip(" -–—:@")
        if len(c) > 1 and c.lower() not in {"we", "they", "i", "now", "still"}:
            return c[:120]
    return ""


def title_of(text: str) -> str:
    """推文没有标题行，取第一条包含岗位词的句子当标题。"""
    m = ROLE_AFTER_RE.search(text) or ROLE_AFTER2_RE.search(text)
    if m:
        role = re.sub(r"https?://\S+", "", m.group(1)).strip(" -–—:#*")
        # 砍掉招聘号统一拼接的模板尾巴（"This is a full time position..."）
        role = re.split(
            r"\.\s*(?:This is a|The position|Apply|Location|Salary)\b|\s+#\w", role, 1, re.I
        )[0].strip(" .-–—")
        if len(role) > 5:
            return role[:200]
    for chunk in re.split(r"[\n。.!?|•·]+", text):
        c = re.sub(r"https?://\S+", "", chunk).strip(" -–—:#*")
        if len(c) > 8 and ROLE_RE.search(c):
            return c[:200]
    return re.sub(r"https?://\S+", "", text).strip()[:200] or "X 招聘帖"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-confidence", type=int, default=50,
                    help="账号置信度低于此值就不取它的帖子")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    raw = json.loads(RAW.read_text(encoding="utf-8")) if RAW.exists() else {}
    tags = json.loads(TAGS.read_text(encoding="utf-8")) if TAGS.exists() else {}

    scraped_at = datetime.fromtimestamp(RAW.stat().st_mtime, tz=timezone.utc).replace(tzinfo=None) if RAW.exists() else None
    rows, skipped_acct = [], 0
    for handle, d in raw.items():
        t = tags.get(handle) or {}
        if t.get("spam"):
            skipped_acct += 1
            continue
        if (t.get("confidence") or 0) < args.min_confidence:
            skipped_acct += 1
            continue
        for i, text in enumerate(d.get("tweets") or []):
            text = html.unescape(text)
            if not is_job(text):
                continue
            links = [u for u in URL_RE.findall(text) if "twitter.com" not in u]
            sal = SALARY_RE.search(text)
            locs = list(dict.fromkeys(LOC_RE.findall(text)))[:3]
            skills = [s for s in SKILLS if re.search(rf"\b{re.escape(s)}\b", text, re.I)]
            rows.append({
                "channel": "x",
                "external_id": hashlib.md5(f"{handle}:{i}:{text[:80]}".encode()).hexdigest()[:24],
                "title": title_of(text),
                "company": (company_of(text) or f"@{handle}")[:250],
                "salary": (sal.group(0).strip() if sal else "")[:64],
                "city": ("Remote" if REMOTE_RE.search(text) else (locs[0] if locs else ""))[:64],
                "experience": "",
                "education": "",
                "skills": sorted(set(skills))[:12],
                "description": text[:4000],
                "url": (links[0] if links else f"https://x.com/{handle}")[:512],
                "raw": {
                    "source_account": handle,
                    "account_confidence": t.get("confidence"),
                    "account_value_score": t.get("value_score"),
                    "account_roles": t.get("roles") or [],
                    "china_friendly": t.get("china_friendly"),
                    "regions": locs,
                    "has_apply_link": bool(links),
                    "posted_at": scraped_at.isoformat() if scraped_at else None,
                },
            })

    dedup = {r["external_id"]: r for r in rows}
    rows = list(dedup.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[x] 账号 {len(raw)} 个（跳过 {skipped_acct}），去重后岗位 {len(rows)} 条 -> {OUT}",
          file=sys.stderr)
    print(f"[x] 其中带申请链接 {sum(1 for r in rows if r['raw']['has_apply_link'])} 条", file=sys.stderr)

    if args.no_db:
        return
    from app.core.models import Job
    from app.db.persist import persist_scraped_jobs
    persist_scraped_jobs([Job(**r) for r in rows], lens_only=True)
    print("[x] 已写入 scraped_jobs", file=sys.stderr)


if __name__ == "__main__":
    main()
