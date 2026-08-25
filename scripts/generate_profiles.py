"""批量预生成高匹配职位画像，写入 job_profiles 缓存。"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import text

from app.api.routes.jobs import PROMPT
from app.core.resume import resume_text
from app.db.connection import engine
from app.infra.local_ai import LocalAiError, run_sync


def _prompt(row: dict, resume: str) -> str:
    return PROMPT.format(
        resume=resume,
        title=row["title"] or "",
        company=row["company"] or "",
        salary=row["salary"] or "未写",
        city=row["city"] or "未写",
        skills=", ".join(json.loads(row["skills"]) if isinstance(row["skills"], str) else (row["skills"] or [])) or "未写",
        channel=row["channel"],
        description=(row["description"] or "")[:3000],
    )


def _generate(row: dict, resume: str, engine_name: str, timeout: int) -> tuple[dict, dict | None]:
    try:
        return row, run_sync(_prompt(row, resume), engine=engine_name, timeout=timeout)
    except LocalAiError as exc:
        print(f"[ai] {exc}", flush=True)
        return row, None


def _write_profiles(items: list[tuple[dict, dict]]) -> None:
    for start in range(0, len(items), 50):
        chunk = items[start:start + 50]
        params: dict[str, object] = {}
        values = []
        for i, (row, data) in enumerate(chunk):
            values.append(
                f"(:ch{i},:ext{i},:jid{i},:verdict{i},:score{i},:lo{i},:hi{i},:profile{i},:model{i})"
            )
            params.update({
                f"ch{i}": row["channel"], f"ext{i}": row["external_id"], f"jid{i}": row["id"],
                f"verdict{i}": str(data.get("verdict") or "")[:32],
                f"score{i}": int(data.get("fit_score") or row["match_score"] or 0),
                f"lo{i}": int(data.get("salary_min_usd") or 0), f"hi{i}": int(data.get("salary_max_usd") or 0),
                f"profile{i}": json.dumps(data, ensure_ascii=False), f"model{i}": "local-ai-batch",
            })
        sql = """
            INSERT INTO job_profiles
              (channel,external_id,scraped_job_id,verdict,fit_score,salary_min,salary_max,profile,model)
            VALUES %s
            ON CONFLICT(channel,external_id) DO UPDATE SET
              scraped_job_id=excluded.scraped_job_id, verdict=excluded.verdict,
              fit_score=excluded.fit_score, salary_min=excluded.salary_min,
              salary_max=excluded.salary_max, profile=excluded.profile,
              model=excluded.model, generated_at=CURRENT_TIMESTAMP
        """ % ",".join(values)
        with engine.begin() as conn:
            conn.execute(text(sql), params)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=int, default=60)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--engine", default="claude", choices=("claude", "codex"))
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    where = "j.match_score >= :score"
    if not args.refresh:
        where += " AND p.id IS NULL"
    limit = " LIMIT :limit" if args.limit else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT j.id,j.channel,j.external_id,j.title,j.company,j.salary,j.city,
                   j.skills,j.description,j.match_score
            FROM scraped_jobs j
            LEFT JOIN job_profiles p ON p.channel=j.channel AND p.external_id=j.external_id
            WHERE {where} ORDER BY j.match_score DESC{limit}
        """), {"score": args.min_score, "limit": args.limit}).mappings().all()
    jobs = [dict(row) for row in rows]
    print(f"待生成 {len(jobs)} 条", flush=True)
    resume = resume_text()
    completed: list[tuple[dict, dict]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_generate, row, resume, args.engine, args.timeout) for row in jobs]
        for n, future in enumerate(as_completed(futures), 1):
            row, data = future.result()
            if data:
                completed.append((row, data))
            print(f"{n}/{len(jobs)} {'成功' if data else '失败'} · {row['title'][:60]}", flush=True)
            if len(completed) >= 50:
                _write_profiles(completed)
                completed.clear()
    if completed:
        _write_profiles(completed)
    print("画像预生成完成", flush=True)


if __name__ == "__main__":
    main()
