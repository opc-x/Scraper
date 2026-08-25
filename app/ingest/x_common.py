"""X 英文/中文共用：推文转 Job + 全站近 N 天搜索。登录态走 chrome profile `x`。"""

from __future__ import annotations

import asyncio
import hashlib
import html
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.channels.x import XAdapter
from app.core.job_derive import REMOTE_RE as DERIVE_REMOTE
from app.core.job_derive import java_in_title, java_in_title_or_skills
from app.core.models import Job
from app.ingest.contract import run_async
from scripts.import_x_jobs import (
    LOC_RE,
    ROLE_RE,
    SALARY_RE,
    SKILLS,
    URL_RE,
    company_of,
    title_of,
)

DEFAULT_DAYS = 90
ToJob = Callable[[dict], Job | None]


def x_title(text: str, *, extra_role_re: re.Pattern[str] | None = None) -> str:
    title = title_of(text)
    if java_in_title(title):
        return title
    role_re = extra_role_re or ROLE_RE
    for chunk in re.split(r"[\n。.!?|•·]+", text):
        c = re.sub(r"https?://\S+", "", chunk).strip(" -–—:#*")
        if len(c) > 8 and java_in_title(c) and role_re.search(c):
            return c[:200]
    return title


def tweet_to_job(
    tweet: dict,
    *,
    channel: str,
    is_job: Callable[[str], bool],
    title_fn: Callable[[str], str],
    remote_city: str = "Remote",
    loc_re: re.Pattern[str] = LOC_RE,
    ext_prefix: str = "x",
) -> Job | None:
    text = html.unescape(tweet.get("text") or "")
    if not is_job(text):
        return None
    title = title_fn(text)
    if not java_in_title_or_skills(title, description=text, channel=channel):
        return None
    handle = (tweet.get("screen_name") or "").strip()
    sid = str(tweet.get("status_id") or "").strip()
    posted = XAdapter.tweet_time(tweet.get("created_at"))
    links = [
        u for u in URL_RE.findall(text)
        if "twitter.com" not in u and "x.com/" not in u
    ]
    salary = SALARY_RE.search(text)
    locs = list(dict.fromkeys(loc_re.findall(text)))[:3]
    skills = [s for s in SKILLS if re.search(rf"\b{re.escape(s)}\b", text, re.I)]
    if sid:
        ext = f"{ext_prefix}_{sid}"[:64]
        url = f"https://x.com/{handle}/status/{sid}" if handle else (links[0] if links else "")
    else:
        ext = hashlib.md5(f"{handle}:{text[:80]}".encode()).hexdigest()[:24]
        url = links[0] if links else (f"https://x.com/{handle}" if handle else "")
    posted_naive = posted.replace(tzinfo=None).isoformat() if posted else None
    city = remote_city if DERIVE_REMOTE.search(text) else (locs[0] if locs else "")
    return Job(
        channel=channel,
        external_id=ext,
        title=title[:250],
        company=(company_of(text) or (f"@{handle}" if handle else "未知"))[:250],
        salary=(salary.group(0).strip() if salary else "")[:64],
        city=city[:64],
        skills=sorted(set(skills))[:12],
        description=text[:4000],
        url=url[:512],
        raw={
            "source_account": handle,
            "status_id": sid,
            "posted_at": posted_naive,
            "created_at": tweet.get("created_at") or "",
            "has_apply_link": bool(links),
            "lang": channel,
        },
    )


def jobs_from_tweets(
    tweets: list[dict], *, days: int = DEFAULT_DAYS, to_job: ToJob,
) -> list[Job]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows: dict[str, Job] = {}
    for tweet in tweets:
        posted = XAdapter.tweet_time(tweet.get("created_at"))
        if posted and posted < cutoff:
            continue
        job = to_job(tweet)
        if job:
            rows[job.external_id] = job
    return list(rows.values())


def pull_recent(query: str, days: int) -> list[dict]:
    print(f"[x] open chrome, search {days}d: {query[:80]}", flush=True)

    async def _go() -> list[dict]:
        adapter = XAdapter()
        try:
            return await asyncio.to_thread(
                adapter.search_recent_sync, query, max_age_days=days,
            )
        finally:
            await adapter.close()

    return run_async(_go())
