"""X。英文渠道。全站搜近 90 天 Java 招聘帖；入库门槛走 persist 的 ingest_gate。"""

from __future__ import annotations

from app.core.models import Job
from app.ingest.x_common import DEFAULT_DAYS, pull_recent, tweet_to_job, x_title
from app.ingest.x_common import jobs_from_tweets as collect_jobs
from scripts.import_x_jobs import is_job as is_job_en

CHANNEL = "x"
LANG = "en"
IMPLEMENTED = True
NEEDS_LOGIN = True
TITLE = "X"
DEFAULT_QUERY = (
    "java (hiring OR \"we're hiring\" OR \"now hiring\") "
    "(engineer OR developer OR backend OR programmer) -javascript"
)


def tweet_to_en_job(tweet: dict) -> Job | None:
    return tweet_to_job(
        tweet, channel=CHANNEL, is_job=is_job_en, title_fn=x_title,
        remote_city="Remote", ext_prefix="x",
    )


def jobs_from_tweets(tweets: list[dict], *, days: int = DEFAULT_DAYS) -> list[Job]:
    return collect_jobs(tweets, days=days, to_job=tweet_to_en_job)


def pull(*, days: int = DEFAULT_DAYS, keyword: str = "") -> list[Job]:
    query = (keyword or "").strip() or DEFAULT_QUERY
    return jobs_from_tweets(pull_recent(query, days), days=days)
