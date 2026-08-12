import logging
from datetime import datetime

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


def persist_scraped_jobs(jobs: list[Job]) -> None:
    if not SessionLocal or not jobs:
        return

    db = SessionLocal()
    try:
        for job in jobs:
            existing = (
                db.query(ScrapedJob)
                .filter_by(channel=job.channel, external_id=job.external_id)
                .first()
            )
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
                    )
                )
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to persist scraped jobs: %s", e)
    finally:
        db.close()
