"""按简历批量给未评分岗位计算 match_score，可中断续跑。"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from sqlalchemy import text

from app.core.resume import HARD_RULES, PROFILE
from app.db.connection import engine
from app.infra.local_ai import run_sync
from app.core.job_quality import evaluate_job

PROMPT = """你是求职岗位匹配评分器。严格按候选人画像和硬性口径给每个岗位打 0-100 分。
Java 后端、分布式、大数据岗位即使标题没写 Java，也要结合描述判断，不能用关键词粗暴判零。
每个分数都必须独立判断；禁止为了省事给多个岗位相同分数。
只输出 JSON 对象：{{"scores":[{{"id":1,"score":85}}]}}。必须覆盖输入中的每个 id，不要解释。

{profile}

{rules}

岗位列表：
{jobs}
"""


def _chunks(rows: list, size: int) -> list:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _skills(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _score_batch(rows: list[dict], engine_name: str, timeout: int) -> tuple[list[dict], dict | None]:
    jobs = [{
        "id": row["id"], "title": row["title"], "company": row["company"],
        "city": row["city"], "skills": _skills(row["skills"]), "salary": row["salary"],
        "description": (row["description"] or "")[:1000],
    } for row in rows]
    prompt = PROMPT.format(profile=PROFILE, rules=HARD_RULES,
                           jobs=json.dumps(jobs, ensure_ascii=False, default=str))
    return rows, run_sync(prompt, engine=engine_name, timeout=timeout)


def _parse_scores(rows: list[dict], data: dict | None) -> list[tuple[int, int]]:
    valid_ids = {int(row["id"]) for row in rows}
    updates = []
    for item in (data or {}).get("scores", []):
        try:
            jid = int(item["id"])
            score = max(0, min(100, int(item["score"])))
        except (KeyError, TypeError, ValueError):
            continue
        if jid in valid_ids:
            updates.append((jid, score))
    return updates if len({jid for jid, _ in updates}) == len(valid_ids) else []


def _write_scores(updates: list[tuple[int, int]]) -> None:
    for chunk in _chunks(updates, 400):
        cases = " ".join(f"WHEN {jid} THEN {score}" for jid, score in chunk)
        ids = ",".join(str(jid) for jid, _ in chunk)
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE scraped_jobs SET match_score=CASE id {cases} END WHERE id IN ({ids})"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--engine", default="claude", choices=("claude", "codex"))
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--days", type=int, default=0, help="0 表示不限制发布时间")
    ap.add_argument("--channel", default="")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    clauses = ["1=1" if args.refresh else "match_score < 0"]
    params: dict[str, object] = {}
    if args.days:
        clauses.append("COALESCE(posted_at, first_seen_at) >= :since")
        params["since"] = (datetime.utcnow() - timedelta(days=args.days)).strftime("%Y-%m-%d %H:%M:%S")
    if args.channel:
        clauses.append("channel = :channel")
        params["channel"] = args.channel
    limit = " LIMIT :limit" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT id,title,company,city,skills,description,salary,url
            FROM scraped_jobs WHERE {' AND '.join(clauses)} ORDER BY id{limit}
        """), params).mappings().all()
    jobs = [dict(row) for row in rows]
    jobs = [row for row in jobs if evaluate_job(
        title=row["title"] or "", description=row["description"] or "", city=row["city"] or "",
        skills=_skills(row["skills"]), salary=row["salary"] or "", url=row["url"] or "",
    ).eligible]
    batches = _chunks(jobs, max(1, args.batch))
    print(f"待评分 {len(jobs)} 条，共 {len(batches)} 批", flush=True)

    pending: list[tuple[int, int]] = []
    done = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_score_batch, batch, args.engine, args.timeout) for batch in batches]
        for future in as_completed(futures):
            batch, data = future.result()
            updates = _parse_scores(batch, data)
            if updates:
                pending.extend(updates)
                done += len(updates)
            else:
                failed += len(batch)
            if len(pending) >= 400:
                _write_scores(pending)
                pending.clear()
            print(f"已评分 {done}/{len(jobs)}，待重试 {failed}", flush=True)
    if pending:
        _write_scores(pending)
    print(f"完成：成功 {done}，失败保留为 -1 的 {failed}", flush=True)


if __name__ == "__main__":
    main()
