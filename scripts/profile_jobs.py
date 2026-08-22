"""批量给职位生成画像（fit_score/verdict/能不能投/风险点/投递建议），
跟 app/api/routes/jobs.py 的 POST /api/jobs/{id}/profile 用同一份 prompt
（app/core/job_profile.py），只是这里走本机 codex/claude CLI 批量跑，不用一条条点。

默认范围：跟产品页「数据」tab 实际展示的口径对齐（近 90 天 + 数据质量过滤 +
排除已归档），且 match_score>=0。缺画像、或旧画像没有招聘意图/职位画像的，都会生成。
可中断续跑：这两项已经有的跳过。

用法：
    python -m scripts.profile_jobs [--min-score 0] [--limit N] [--workers 8]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

from app.core.job_comments import gather_comments
from app.core.job_profile import profile_fields, render_prompt
from app.core.resume import resume_text
from app.db.connection import SessionLocal
from app.db.schema import JobMark, JobProfile, ScrapedJob
from app.infra.local_ai import run_sync

NON_JOB_PHRASES = (
    "hey job seekers", "job roundup", "weekly jobs", "multiple openings",
    "hiring list", "职位合集", "岗位汇总",
)


def _candidates(db, *, min_score: int, within_days: int, channel: str, limit: int) -> list[ScrapedJob]:
    since = datetime.now(timezone.utc) - timedelta(days=within_days)
    text = func.lower(ScrapedJob.title + " " + ScrapedJob.description)
    query = db.query(ScrapedJob).filter(
        ScrapedJob.match_score >= min_score,
        ScrapedJob.posted_at >= since,
        func.length(func.trim(ScrapedJob.title)) > 0,
        func.length(func.trim(ScrapedJob.description)) >= 40,
        ~func.lower(func.trim(ScrapedJob.title)).in_(("software engineering", "remote")),
        ~func.lower(ScrapedJob.title).like("http%"),
        ~func.lower(ScrapedJob.title).like("www.%"),
        ~or_(*[text.like(f"%{p}%") for p in NON_JOB_PHRASES]),
    )
    if channel:
        query = query.filter(ScrapedJob.channel == channel)
    rows = query.all()

    archived = set(db.query(JobMark.channel, JobMark.external_id).filter_by(state="archived").all())
    profiles = {
        (p.channel, p.external_id): (p.profile or {})
        for p in db.query(JobProfile).all()
    }

    def _done(profile: dict) -> bool:
        intent = profile.get("hiring_intent")
        has_intent = (
            bool(intent) if not isinstance(intent, dict)
            else bool(intent.get("type") or intent.get("reason"))
        )
        return has_intent and bool(profile.get("job_portrait"))

    rows = [
        r for r in rows
        if (r.channel, r.external_id) not in archived
        and not _done(profiles.get((r.channel, r.external_id), {}))
    ]
    rows.sort(key=lambda r: r.match_score, reverse=True)
    return rows[:limit] if limit else rows


def _generate_one(row_id: int, title: str, company: str, salary: str, city: str,
                   skills: list, channel: str, description: str, external_id: str,
                   raw: dict | None, resume: str, engine: str, timeout: int) -> tuple[int, dict | None]:
    comments, sources = gather_comments(
        company=company, channel=channel, external_id=external_id or "",
        raw=raw if isinstance(raw, dict) else None,
    )
    prompt = render_prompt(
        resume=resume, title=title, company=company, salary=salary,
        city=city, skills=skills if isinstance(skills, list) else [],
        channel=channel, description=description, comments=comments,
    )
    data = run_sync(prompt, engine=engine, timeout=timeout)
    if data is not None:
        data["comment_sources"] = sources
    return row_id, data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--within-days", type=int, default=90)
    ap.add_argument("--channel", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--engine", default="codex", choices=("codex", "claude"))
    ap.add_argument("--timeout", type=int, default=240)
    args = ap.parse_args()

    if not SessionLocal:
        raise SystemExit("数据库没配置")

    db = SessionLocal()
    try:
        rows = _candidates(
            db, min_score=args.min_score, within_days=args.within_days,
            channel=args.channel, limit=args.limit,
        )
        print(f"待生成画像 {len(rows)} 条", flush=True)
        if not rows:
            return
        resume = resume_text()
        jobs_by_id = {r.id: r for r in rows}

        done = failed = 0
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = [
                pool.submit(
                    _generate_one, r.id, r.title, r.company, r.salary, r.city,
                    r.skills, r.channel, r.description, r.external_id, r.raw,
                    resume, args.engine, args.timeout,
                )
                for r in rows
            ]
            for future in as_completed(futures):
                row_id, data = future.result()
                row = jobs_by_id[row_id]
                if not data:
                    failed += 1
                    print(f"[失败] id={row_id} {row.title[:40]!r}", flush=True)
                    continue
                fields = profile_fields(data, row.salary or "")
                existing = db.query(JobProfile).filter_by(
                    channel=row.channel, external_id=row.external_id
                ).first()
                target = existing or JobProfile(channel=row.channel, external_id=row.external_id)
                target.scraped_job_id = row.id
                target.verdict = fields["verdict"]
                target.fit_score = fields["fit_score"]
                target.salary_min = fields["salary_min"]
                target.salary_max = fields["salary_max"]
                target.profile = data
                target.model = f"{args.engine}-cli"
                if not existing:
                    db.add(target)
                db.commit()
                done += 1
                print(f"已生成 {done}/{len(rows)}，失败 {failed}", flush=True)
    finally:
        db.close()

    print(f"完成：成功 {done}，失败 {failed}", flush=True)


if __name__ == "__main__":
    main()
