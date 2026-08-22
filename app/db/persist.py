import logging
from datetime import datetime, timezone

from app.core.models import Job
from app.db.connection import SessionLocal
from app.db.schema import MinedAccount, ScrapedJob, XAccount

logger = logging.getLogger(__name__)


def profile_to_x_account_fields(screen_name: str, profile: dict) -> dict:
    """把 XAdapter.extract_user_profile 抓到的原始 profile dict，摘成 XAccount 的字段。"""
    core = profile.get("core", {})
    rel = profile.get("relationship_counts", {})
    tweet_counts = profile.get("tweet_counts", {})
    return {
        "rest_id": str(profile.get("rest_id", "")),
        "screen_name": screen_name,
        "name": core.get("name", ""),
        "bio": profile.get("profile_bio", {}).get("description", ""),
        "location": profile.get("location", {}).get("location", ""),
        "website_url": profile.get("website", {}).get("url", ""),
        "avatar_url": profile.get("avatar", {}).get("image_url", ""),
        "banner_url": profile.get("banner", {}).get("image_url", ""),
        "x_created_at": core.get("created_at", ""),
        "followers_count": rel.get("followers", 0),
        "following_count": rel.get("following", 0),
        "tweets_count": tweet_counts.get("tweets", 0),
        "media_tweets_count": tweet_counts.get("media_tweets", 0),
        "favorites_count": profile.get("action_counts", {}).get("favorites_count", 0),
        "is_blue_verified": profile.get("is_blue_verified", False),
        "verified": profile.get("verification", {}).get("verified", False),
        "protected": profile.get("privacy", {}).get("protected", False),
        "pinned_tweet_ids": profile.get("pinned_items", {}).get("tweet_ids_str", []),
        "raw": profile,
    }


def persist_x_accounts(accounts: list[dict]) -> None:
    """accounts 每条: profile_to_x_account_fields() 的返回值。按 rest_id upsert。"""
    if not SessionLocal or not accounts:
        return

    db = SessionLocal()
    try:
        for a in accounts:
            existing = db.query(XAccount).filter_by(rest_id=a["rest_id"]).first()
            if existing:
                for k, v in a.items():
                    setattr(existing, k, v)
                existing.synced_at = datetime.utcnow()
            else:
                db.add(XAccount(**a))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist x accounts: %s", e)
    finally:
        db.close()


def persist_mined_accounts(channel: str, topic: str, accounts: list[dict]) -> None:
    """accounts 每条: {handle, profile_url, bio, confidence, value_score, kept, tags, rationale}"""
    if not SessionLocal or not accounts:
        return

    db = SessionLocal()
    try:
        for a in accounts:
            existing = (
                db.query(MinedAccount)
                .filter_by(channel=channel, topic=topic, handle=a["handle"])
                .first()
            )
            if existing:
                existing.profile_url = a.get("profile_url", "")
                existing.bio = a.get("bio", "")
                existing.confidence = a["confidence"]
                existing.value_score = a.get("value_score", 0)
                existing.kept = a.get("kept", True)
                existing.tags = a.get("tags", [])
                existing.rationale = a.get("rationale", "")
            else:
                db.add(
                    MinedAccount(
                        channel=channel,
                        topic=topic,
                        handle=a["handle"],
                        profile_url=a.get("profile_url", ""),
                        bio=a.get("bio", ""),
                        confidence=a["confidence"],
                        value_score=a.get("value_score", 0),
                        kept=a.get("kept", True),
                        tags=a.get("tags", []),
                        rationale=a.get("rationale", ""),
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist mined accounts: %s", e)
    finally:
        db.close()


PERSIST_BATCH_SIZE = 25


def _parse_posted_at(job: Job) -> datetime | None:
    raw_posted_at = (job.raw or {}).get("posted_at") or (job.raw or {}).get("published_at")
    if not raw_posted_at:
        return None
    try:
        posted_at = datetime.fromisoformat(str(raw_posted_at).replace("Z", "+00:00"))
        if posted_at.tzinfo:
            posted_at = posted_at.astimezone(timezone.utc).replace(tzinfo=None)
        return posted_at
    except ValueError:
        return None


def persist_scraped_jobs(jobs: list[Job]) -> None:
    """一个连接跑到底，只按 PERSIST_BATCH_SIZE 分批 commit（不重开连接/session）。

    Turso 远程每次查询往返有明显延迟，之前对每条 job 单独 SELECT 一次存在性、
    再塞进一个大事务一次性 commit，200+ 条时经常在提交前超时整体回滚（电鸭抓
    200+ 条时踩过这个坑）。现在改成：先用一条 IN 查询批量取出已存在的行，
    之后只在内存里比对增/改，且每 PERSIST_BATCH_SIZE 条 commit 一次——一批
    出错只丢那一批，不影响已经落库的其它批次；重开 session 本身在这条链路上
    也有几秒的握手开销，所以全程复用同一个 session。
    """
    if not SessionLocal or not jobs:
        return

    db = SessionLocal()
    persisted_any = False
    try:
        by_channel: dict[str, list[Job]] = {}
        for job in jobs:
            by_channel.setdefault(job.channel, []).append(job)

        existing_by_key: dict[tuple[str, str], ScrapedJob] = {}
        for channel, channel_jobs in by_channel.items():
            ids = [j.external_id for j in channel_jobs]
            for start in range(0, len(ids), PERSIST_BATCH_SIZE):
                chunk = ids[start : start + PERSIST_BATCH_SIZE]
                rows = (
                    db.query(ScrapedJob)
                    .filter(ScrapedJob.channel == channel, ScrapedJob.external_id.in_(chunk))
                    .all()
                )
                for row in rows:
                    existing_by_key[(row.channel, row.external_id)] = row

        for start in range(0, len(jobs), PERSIST_BATCH_SIZE):
            batch = jobs[start : start + PERSIST_BATCH_SIZE]
            try:
                for job in batch:
                    parsed = _parse_posted_at(job)
                    existing = existing_by_key.get((job.channel, job.external_id))
                    if existing:
                        existing.title = job.title
                        existing.company = job.company
                        existing.salary = job.salary
                        existing.city = job.city
                        existing.experience = job.experience
                        existing.education = job.education
                        existing.skills = job.skills
                        existing.description = job.description
                        existing.url = job.url
                        existing.raw = job.raw
                        existing.last_seen_at = datetime.utcnow()
                        if parsed:
                            existing.posted_at = parsed
                        elif not existing.posted_at:
                            existing.posted_at = existing.first_seen_at or datetime.utcnow()
                    else:
                        db.add(
                            ScrapedJob(
                                channel=job.channel,
                                external_id=job.external_id,
                                title=job.title,
                                company=job.company,
                                salary=job.salary,
                                city=job.city,
                                experience=job.experience,
                                education=job.education,
                                skills=job.skills,
                                description=job.description,
                                url=job.url,
                                raw=job.raw,
                                posted_at=parsed or datetime.utcnow(),
                            )
                        )
                db.commit()
                persisted_any = True
            except Exception as e:
                db.rollback()
                logger.error(
                    "Failed to persist scraped jobs batch %d-%d: %s",
                    start,
                    start + len(batch),
                    e,
                )
    finally:
        db.close()

    if persisted_any:
        from app.api.routes.scraped import invalidate_scraped_cache

        invalidate_scraped_cache()
