"""修复被写成整段正文的岗位标题。

HN 的 who-is-hiring 评论惯例是首行 "公司 | 岗位 | 地点 | 技术栈"，
但不少人首行直接写公司简介，于是标题变成一整段话。这里从正文里
重新找一个像岗位名的片段替换掉。

用法：
    python -m scripts.fix_job_titles --dry-run
    python -m scripts.fix_job_titles
"""

from __future__ import annotations

import argparse
import re
import sys

from sqlalchemy import text

from app.db.connection import engine

ROLE_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|junior|jr\.?|mid|head of)?\s*"
    r"(?:[\w+#/.-]+\s+){0,3}"
    r"(?:engineer|engineering manager|developer|programmer|architect|scientist|"
    r"devops|sre|analyst|designer|manager|specialist|consultant|intern)"
    r"(?:\s*[-–—,(]\s*[^\n|]{0,40})?", re.I)
NOISE_PREFIX = re.compile(
    r"^(?:remote\s*\([^)]*\)|remote|onsite|hybrid|hiring|we[''`]?re hiring|now hiring|"
    r"\d+x?)\s*[:\-–—|]?\s*", re.I)
# "to our Recruiting Manager" 这种碎片不是岗位名，得挡掉
FRAGMENT_RE = re.compile(r"^(to|at|for|with|and|or|the|an?|our|your|as|by|from|in|on)\b", re.I)
SENTENCE = re.compile(r"\b(we are|we're|our team|is an?|is the|founded|backed by|"
                      r"anyone here|i'm|i am|looking for tips)\b", re.I)


# 开头就是残句/标点的，多半是从推文正文里截歪了（"re a backend engineer"、"+ Principal Engineer"）
# 撇号被吃掉后留下的残词（we're → re），以及以标点开头的
JUNK_HEAD_RE = re.compile(r"^\s*(?:[+\-–—•*,.:;)\]]|(?:re|ve|ll|s|t|m|d)\b)", re.I)


def looks_broken(title: str) -> bool:
    t = (title or "").strip()
    if not t:
        return True
    if len(t) > 70 or SENTENCE.search(t):
        return True
    # 去掉 emoji 前缀再判断开头
    # 先看原串开头的标点，再看去掉 emoji 后的首词
    if JUNK_HEAD_RE.match(t):
        return True
    # 整串没有一个大写开头的词 = 多半是从正文里截的散句，不是岗位名
    words = re.findall(r"[A-Za-z][\w+#.]*", t)
    if len(words) >= 3 and not any(w[0].isupper() for w in words):
        return True
    core = re.sub(r"^[^\w(]+", "", t)
    return bool(JUNK_HEAD_RE.match(core))


def better_title(title: str, description: str, company: str) -> str | None:
    """返回更好的标题；没有更好的就返回 None。"""
    if not looks_broken(title):
        return None

    # 惯例格式：公司 | 岗位 | 地点 | 技术栈，第二段就是岗位
    for line in (description or "").split("\n")[:3]:
        parts = [p.strip() for p in re.split(r"\s*[|｜]\s*", line) if p.strip()]
        if (len(parts) >= 2 and 4 < len(parts[1]) <= 70
                and ROLE_RE.search(parts[1]) and not FRAGMENT_RE.match(parts[1])):
            return parts[1]

    # 退而求其次：正文里第一个像岗位名的片段
    # 残词头要先剥掉再找岗位名，否则 "re a backend engineer" 会原样匹配回自己
    cleaned = NOISE_PREFIX.sub("", JUNK_HEAD_RE.sub("", title).strip())
    m = ROLE_RE.search(cleaned)
    if not m:
        m = ROLE_RE.search(description or "")
    if m:
        cand = re.sub(r"\s+", " ", m.group(0)).strip(" -–—,:|(")
        # "a backend engineer" 这种，把开头的冠词/介词剥掉再用
        while FRAGMENT_RE.match(cand):
            stripped = FRAGMENT_RE.sub("", cand, count=1).strip(" -–—,:|(")
            if not stripped or stripped == cand:
                break
            cand = stripped
        if 4 < len(cand) <= 70:
            return cand[:1].upper() + cand[1:]

    # 实在抠不出来就截断，至少别让整段话当标题
    head = re.sub(r"\s+", " ", title).strip()
    return (head[:67] + "…") if len(head) > 70 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, title, description, company FROM scraped_jobs"
        )).fetchall()
    rows = [r for r in rows if looks_broken(r[1])]
    print(f"候选 {len(rows)} 条", flush=True)

    fixes = []
    for jid, title, desc, company in rows:
        nt = better_title(title or "", desc or "", company or "")
        if nt and nt != title:
            fixes.append((jid, nt))
    print(f"可修复 {len(fixes)} 条", flush=True)
    for jid, nt in fixes[:12]:
        print(f"  → {nt[:70]}", flush=True)

    if args.dry_run or not fixes:
        return
    for i in range(0, len(fixes), 300):
        chunk = fixes[i:i + 300]
        cases = " ".join(
            "WHEN {} THEN '{}'".format(jid, nt.replace("'", "''")) for jid, nt in chunk)
        ids = ",".join(str(jid) for jid, _ in chunk)
        with engine.begin() as c:
            c.execute(text(f"UPDATE scraped_jobs SET title = CASE id {cases} END WHERE id IN ({ids})"))
        print(f"  已修 {min(i + 300, len(fixes))}/{len(fixes)}", flush=True)
    print("完成", flush=True)


if __name__ == "__main__":
    main()
