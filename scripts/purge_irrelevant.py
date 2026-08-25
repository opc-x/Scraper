"""删掉跟简历方向完全不沾边的职位。

只删「一眼就不是后端/数据/基础设施」的（设计、销售、市场、客服、医护、司机…），
技术岗但不是 Java 主栈的不删 —— 那个交给匹配度分数去排序，不该在这一步一刀切。

用法：
    python -m scripts.purge_irrelevant --dry-run
    python -m scripts.purge_irrelevant
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter

from sqlalchemy import text

from app.db.connection import engine

# 命中即删：这些方向跟 Java 后端 / 大数据没有任何交集
KILL_RE = re.compile(
    r"\b("
    r"designer|design engineer|ux|ui designer|graphic|illustrat|animator|video editor|"
    r"sales|account executive|business development|bd manager|partnership|"
    r"marketing|seo|sem|growth marketer|paid media|content writer|copywriter|"
    r"social media|community manager|influencer|"
    r"customer (support|success|service)|support (agent|specialist|representative)|helpdesk|"
    r"recruiter|talent acquisition|hr |human resources|people ops|"
    r"nurse|physician|practitioner|therapist|dental|pharmacy|medical|caregiver|specimen|"
    r"driver|delivery|warehouse|logistics coordinator|store manager|retail|barista|cleaner|"
    r"security guard|janitor|"
    r"teacher|tutor|instructor|curriculum|"
    r"accountant|bookkeep|payroll|paralegal|legal counsel|"
    r"executive assistant|virtual assistant|receptionist|data entry|transcription|"
    r"translator|interpreter|voice over|"
    r"product manager|program manager|project manager|scrum master|business analyst|"
    r"technical writer|documentation specialist"
    r")\b", re.I)

# 例外：标题里同时出现这些词就留着（比如 "Engineering Manager, Backend"）
KEEP_RE = re.compile(
    r"\b(backend|back[- ]end|server[- ]?side|java|scala|kotlin|spring|jvm|"
    r"data engineer|data platform|big data|hadoop|spark|flink|hive|kafka|"
    r"distributed|infrastructure|platform engineer|sre|devops|"
    r"software engineer|engineering manager|architect|"
    r"infra|full[- ]?stack|ai engineer|ml engineer|machine learning|llm|"
    r"golang|\bgo engineer|rust|python|node|microservice|api engineer|"
    r"database|storage|observability|streaming|etl|warehouse engineer)\b", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with engine.connect() as c:
        rows = c.execute(text("SELECT id, channel, title FROM scraped_jobs")).fetchall()

    doomed = [
        (jid, ch, title) for jid, ch, title in rows
        if KILL_RE.search(title or "") and not KEEP_RE.search(title or "")
    ]
    by_ch = Counter(ch for _, ch, _ in doomed)
    print(f"总共 {len(rows)} 条，判定为无关的 {len(doomed)} 条 {dict(by_ch)}", file=sys.stderr)
    print("样本：", file=sys.stderr)
    for _, ch, title in doomed[:15]:
        print(f"  [{ch}] {title[:70]}", file=sys.stderr)

    if args.dry_run or not doomed:
        return

    ids = [str(jid) for jid, _, _ in doomed]
    for i in range(0, len(ids), 400):
        chunk = ",".join(ids[i:i + 400])
        with engine.begin() as c:
            # 标记表里的对应记录也一并清掉，免得「我的」里留着指向已删职位的孤儿
            c.execute(text(f"DELETE FROM scraped_jobs WHERE id IN ({chunk})"))
        print(f"  已删 {min(i + 400, len(ids))}/{len(ids)}", flush=True)
    print(f"删除完成 {len(ids)} 条", flush=True)


if __name__ == "__main__":
    main()
