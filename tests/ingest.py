import json
from pathlib import Path

import pytest

from app.core.job_derive import _lens_lang
from app.ingest.contract import CHANNEL_LANG, lang_for
from app.ingest.liepin import pull as pull_liepin
from app.ingest.registry import CHANNELS, specs


def test_ingest_contract_one_file_per_channel():
    rows = specs()
    names = [row.channel for row in rows]
    assert names == [
        "boss", "v2ex", "eleduck", "telegram", "discord", "x", "x_zh",
        "hackernews", "remoteok", "weworkremotely", "liepin", "zhilian",
    ]
    for row in rows:
        mod = CHANNELS[row.channel]
        assert hasattr(mod, "pull")
        assert row.lang == CHANNEL_LANG[row.channel] == mod.LANG


def test_lang_contract_matches_lens():
    assert lang_for("boss") == "zh"
    assert lang_for("discord") == "en"
    assert lang_for("x_zh") == "zh"
    assert lang_for("telegram") == "both"
    assert _lens_lang("v2ex") == "zh"
    assert _lens_lang("hackernews") == "en"
    assert _lens_lang("telegram") == "both"


def test_unimplemented_channels_raise():
    with pytest.raises(NotImplementedError, match="liepin"):
        pull_liepin()


def test_discord_pull_reads_dump(tmp_path: Path):
    dump = tmp_path / "discord.jsonl"
    dump.write_text(
        json.dumps({
            "type": "jobs",
            "batch": [{
                "guildId": "1",
                "guild": "CronJobs",
                "channel": "all-jobs",
                "threadId": "99",
                "name": "Hiring: Remote Java Backend Developer",
                "content": "Worldwide remote Java engineer. Non-US ok.",
                "apply": [],
                "ts": "2026-08-01T00:00:00.000Z",
            }],
        }) + "\n",
        encoding="utf-8",
    )
    from app.ingest.discord import pull

    jobs = pull(path=str(dump))
    assert len(jobs) == 1
    assert jobs[0].channel == "discord"
    assert jobs[0].external_id == "dc_99"


def test_x_jobs_from_tweets_java_title_then_90d():
    from app.ingest.x import jobs_from_tweets

    tweets = [
        {
            "text": "We're hiring a Senior Java Engineer, remote, $150k. Apply now.",
            "screen_name": "acme",
            "status_id": "11",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "We're hiring a Senior Python Engineer, remote. Apply now.",
            "screen_name": "acme",
            "status_id": "12",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "We're hiring a Senior Java Engineer, remote. Apply now.",
            "screen_name": "acme",
            "status_id": "13",
            "created_at": "Wed Jan 01 00:00:00 +0000 2020",
        },
        {
            "text": "Stack: Java Spring Kafka. We're hiring a Backend Engineer, remote. Apply.",
            "screen_name": "acme",
            "status_id": "14",
            "created_at": "Mon Aug 20 00:00:00 +0000 2026",
        },
    ]
    jobs = jobs_from_tweets(tweets, days=90)
    ids = {j.external_id for j in jobs}
    assert ids == {"x_11", "x_14"}
    job = next(j for j in jobs if j.external_id == "x_11")
    assert "Java" in job.title
    assert job.raw["posted_at"].startswith("2026-08-11")
    body = next(j for j in jobs if j.external_id == "x_14")
    assert "Java" in body.description


def test_x_zh_jobs_from_tweets_java_title_then_90d():
    from app.ingest.x_zh import jobs_from_tweets_zh

    tweets = [
        {
            "text": "急招远程Java开发工程师，Spring Boot，可居家办公。",
            "screen_name": "hr_zhang",
            "status_id": "21",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "We're hiring a Senior Java Engineer, remote. Apply now.",
            "screen_name": "acme",
            "status_id": "22",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "本人求职 Java 开发，杭州。",
            "screen_name": "seeker",
            "status_id": "23",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "急招远程Java开发工程师，杭州。",
            "screen_name": "hr_zhang",
            "status_id": "24",
            "created_at": "Wed Jan 01 00:00:00 +0000 2020",
        },
        {
            "text": "急招后端开发，技术栈 Java Spring，可远程居家办公。",
            "screen_name": "hr_zhang",
            "status_id": "25",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
        {
            "text": "Java 太卷了，一个岗位几十上百个人投。",
            "screen_name": "rant",
            "status_id": "26",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
    ]
    jobs = jobs_from_tweets_zh(tweets, days=90)
    ids = {j.external_id for j in jobs}
    assert ids == {"xzh_21", "xzh_25"}
    job = next(j for j in jobs if j.external_id == "xzh_21")
    assert job.channel == "x_zh"
    assert job.city == "远程"
    body = next(j for j in jobs if j.external_id == "xzh_25")
    assert "Java" in body.description
