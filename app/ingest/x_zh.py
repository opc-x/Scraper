"""X 中文。全站搜近 90 天中文 Java 招聘帖；登录态与英文 X 共用。"""

from __future__ import annotations

import re

from app.core.job_derive import java_in_title
from app.core.models import Job
from app.ingest.x_common import DEFAULT_DAYS, jobs_from_tweets, pull_recent, tweet_to_job, x_title

CHANNEL = "x_zh"
LANG = "zh"
IMPLEMENTED = True
NEEDS_LOGIN = True
TITLE = "X 中文"
DEFAULT_QUERY = "Java (招聘 OR 急招 OR 招人)"

_ZH_HIRING = re.compile(r"招聘|急招|招人|招新|招(?:一)?名|寻\s*Java|\bHC\b")
_ZH_JAVA = re.compile(r"(?<![a-zA-Z])java(?![a-zA-Z])", re.I)
_ZH_SEEKING = re.compile(r"求职|找工作|本人.*求职")
_ZH_TITLE_AFTER = re.compile(
    r"(?:招聘|急招|招人|招)\s*(?:远程)?\s*"
    r"(Java\s*(?:开发(?:工程师)?|工程师|后端)[^\n。.!?]{0,40})",
    re.I,
)
_ZH_LOC = re.compile(r"杭州|上海|北京|深圳|广州|成都|武汉|南京|远程|居家")
_ZH_ROLE_WORD = re.compile(r"工程师|开发|后端|engineer|developer|programmer", re.I)


def is_job(text: str) -> bool:
    if _ZH_SEEKING.search(text) and not _ZH_HIRING.search(text):
        return False
    return bool(_ZH_HIRING.search(text) and _ZH_JAVA.search(text))


def zh_title(text: str) -> str:
    hit = _ZH_TITLE_AFTER.search(text)
    if hit and java_in_title(hit.group(1)):
        return hit.group(1).strip(" -–—:#*")[:200]
    return x_title(text, extra_role_re=_ZH_ROLE_WORD)


def tweet_to_zh_job(tweet: dict) -> Job | None:
    return tweet_to_job(
        tweet, channel=CHANNEL, is_job=is_job, title_fn=zh_title,
        remote_city="远程", loc_re=_ZH_LOC, ext_prefix="xzh",
    )


def jobs_from_tweets_zh(tweets: list[dict], *, days: int = DEFAULT_DAYS) -> list[Job]:
    return jobs_from_tweets(tweets, days=days, to_job=tweet_to_zh_job)


def pull(*, days: int = DEFAULT_DAYS, keyword: str = "") -> list[Job]:
    query = (keyword or "").strip() or DEFAULT_QUERY
    return jobs_from_tweets_zh(pull_recent(query, days), days=days)
