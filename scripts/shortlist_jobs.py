"""从 scraped_jobs 里筛出「你真正能投」的岗位短名单。

打分维度（都是硬信号，不用 LLM）：
  有申请链接 > 远程 > 技术栈命中 > 薪资披露 > 无地域硬限制
跨渠道按 (公司, 岗位) 去重 —— 同一个岗位常被多个 TG 频道转发。

用法：
    python -m scripts.shortlist_jobs --stack node,python,java,agent --top 150
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

from sqlalchemy import text

from app.db.connection import engine

STACK_PATTERNS = {
    "node": r"\bnode(?:\.?js)?\b|\bexpress\b|\bnest(?:js)?\b|\btypescript\b",
    "python": r"\bpython\b|\bdjango\b|\bfastapi\b|\bflask\b",
    "java": r"\bjava\b(?!script)|\bspring\b|\bkotlin\b",
    "agent": r"\b(ai agent|agentic|llm|rag|langchain|langgraph|mcp|openai|anthropic|"
             r"prompt engineer|genai|vector (db|database))\b",
}
# 明确把中国大陆排除在外的措辞，命中就降权
BLOCKED_RE = re.compile(
    r"\b(must be (?:located|based) in|only (?:in|for)|authorized to work in|"
    r"work authorization|us citizen|security clearance|eligible to work in|"
    r"no (?:visa )?sponsorship|onsite only|hybrid)\b", re.I)
FRIENDLY_RE = re.compile(
    r"\b(worldwide|anywhere|global(?:ly)?|any time ?zone|fully remote|remote[- ]first|"
    r"work from anywhere|no location requirement)\b", re.I)
SENIOR_RE = re.compile(r"\b(senior|sr\.?|staff|principal|lead)\b", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", default="node,python,java,agent")
    ap.add_argument("--top", type=int, default=150)
    ap.add_argument("--out", default="data/shortlist.md")
    ap.add_argument("--json-out", default="data/shortlist.json")
    args = ap.parse_args()

    wanted = [s.strip() for s in args.stack.split(",") if s.strip()]
    pats = {k: re.compile(v, re.I) for k, v in STACK_PATTERNS.items() if k in wanted}

    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT channel, title, company, salary, city, skills, description, url, raw "
            "FROM scraped_jobs"
        )).fetchall()

    scored = []
    for ch, title, company, salary, city, skills, desc, url, raw in rows:
        blob = f"{title} {company} {city} {skills} {desc}"
        hits = [k for k, p in pats.items() if p.search(blob)]
        if not hits:
            continue

        try:
            rawd = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            rawd = {}

        has_link = bool(url) and not url.startswith("https://t.me/") and not url.startswith("https://x.com/")
        is_remote = bool(rawd.get("is_remote")) or bool(re.search(r"\bremote\b|远程", f"{city} {blob}", re.I))
        has_salary = bool(salary) and salary not in ("未披露", "面议", "")
        blocked = bool(BLOCKED_RE.search(desc or ""))
        friendly = bool(FRIENDLY_RE.search(desc or ""))

        score = 0
        score += 40 if has_link else 0          # 投不了的排后面，这条权重最大
        score += 20 if is_remote else 0
        score += 10 * len(hits)
        score += 12 if has_salary else 0
        score += 15 if friendly else 0
        score -= 18 if blocked else 0
        score += 5 if SENIOR_RE.search(title or "") else 0

        scored.append({
            "score": score, "channel": ch, "title": (title or "").strip(),
            "company": (company or "").strip(), "salary": salary or "", "city": city or "",
            "stack_hits": hits, "url": url or "", "has_link": has_link,
            "is_remote": is_remote, "location_blocked": blocked, "location_friendly": friendly,
            "source": rawd.get("source_channel") or rawd.get("source_account")
                      or rawd.get("source_server") or ch,
        })

    # 同一岗位常被多个频道转发，按 (公司, 岗位) 留分最高的一条
    best: dict[tuple, dict] = {}
    for r in scored:
        key = (norm(r["company"]), norm(r["title"])[:60])
        if key not in best or r["score"] > best[key]["score"]:
            best[key] = r
    rows_out = sorted(best.values(), key=lambda r: r["score"], reverse=True)[: args.top]

    Path(args.json_out).write_text(json.dumps(rows_out, ensure_ascii=False, indent=2), encoding="utf-8")

    by_stack = defaultdict(int)
    for r in rows_out:
        for h in r["stack_hits"]:
            by_stack[h] += 1

    L = ["# 可投岗位短名单", ""]
    L.append(f"从 {len(rows)} 条抓取结果里，命中技术栈 {len(scored)} 条，"
             f"跨渠道去重后 {len(best)} 条，取前 {len(rows_out)} 条。")
    L.append("")
    L.append("方向分布：" + " · ".join(f"{k} {v}" for k, v in sorted(by_stack.items(), key=lambda x: -x[1])))
    L.append("")
    L.append("| # | 岗位 | 公司 | 薪资 | 地点 | 方向 | 渠道 | 投递 |")
    L.append("|---:|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows_out, 1):
        flag = "⚠️" if r["location_blocked"] else ("🌍" if r["location_friendly"] else "")
        link = f"[申请]({r['url']})" if r["has_link"] else "无链接"
        L.append(
            f"| {i} | {r['title'][:60]} | {r['company'][:28]} | {r['salary'][:20]} | "
            f"{flag}{r['city'][:22]} | {','.join(r['stack_hits'])} | {r['channel']} | {link} |"
        )
    L += ["", "⚠️ = 描述里有地域/工作许可硬限制  🌍 = 明确写了 worldwide / 任意时区"]
    Path(args.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"-> {args.out}（{len(rows_out)} 条，其中有申请链接 "
          f"{sum(1 for r in rows_out if r['has_link'])} 条）")


if __name__ == "__main__":
    main()
