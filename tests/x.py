import json

from app.channels.x import XAdapter
from app.infra import llm

SAMPLE_SEARCH_RESPONSE = {
    "data": {
        "search_by_raw_query": {
            "search_timeline": {
                "timeline": {
                    "instructions": [
                        {
                            "type": "TimelineAddEntries",
                            "entries": [
                                {
                                    "entryId": "tweet-1",
                                    "content": {
                                        "itemContent": {
                                            "tweet_results": {
                                                "result": {
                                                    "core": {
                                                        "user_results": {
                                                            "result": {
                                                                "legacy": {
                                                                    "screen_name": "hiring_bot",
                                                                    "name": "Hiring Bot",
                                                                }
                                                            }
                                                        }
                                                    },
                                                    "legacy": {
                                                        "id_str": "1234567890",
                                                        "full_text": (
                                                            "We're hiring a Senior Python "
                                                            "Engineer, remote, $150k-$180k. DM me."
                                                        ),
                                                        "created_at": (
                                                            "Mon Aug 11 00:00:00 +0000 2026"
                                                        ),
                                                    },
                                                }
                                            }
                                        }
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        }
    }
}


def test_extract_tweets_walks_nested_graphql_payload():
    tweets = XAdapter.extract_tweets(SAMPLE_SEARCH_RESPONSE)

    assert len(tweets) == 1
    assert tweets[0]["screen_name"] == "hiring_bot"
    assert "Python Engineer" in tweets[0]["text"]
    assert tweets[0]["created_at"] == "Mon Aug 11 00:00:00 +0000 2026"
    assert tweets[0]["status_id"] == "1234567890"


def test_extract_tweets_reads_screen_name_from_nested_core():
    # 真实 X 响应里用户名/昵称在 result.core 而不是 result.legacy（2026-08 抓包实测确认）
    payload = {
        "core": {
            "user_results": {
                "result": {
                    "core": {"screen_name": "hiring_bot", "name": "Hiring Bot"},
                }
            }
        },
        "legacy": {
            "full_text": "We're hiring a Senior Python Engineer, remote.",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
    }

    tweets = XAdapter.extract_tweets(payload)

    assert len(tweets) == 1
    assert tweets[0]["screen_name"] == "hiring_bot"
    assert tweets[0]["name"] == "Hiring Bot"


def test_extract_tweets_reads_bio_from_profile_bio():
    # bio 同一次迁移挪到了 result.profile_bio.description（2026-08 抓包实测确认）
    payload = {
        "core": {
            "user_results": {
                "result": {
                    "core": {"screen_name": "hiring_bot", "name": "Hiring Bot"},
                    "profile_bio": {"description": "Daily remote job alerts 🌍"},
                }
            }
        },
        "legacy": {
            "full_text": "We're hiring a Senior Python Engineer, remote.",
            "created_at": "Mon Aug 11 00:00:00 +0000 2026",
        },
    }

    tweets = XAdapter.extract_tweets(payload)

    assert tweets[0]["bio"] == "Daily remote job alerts 🌍"


def test_extract_tweets_empty_payload_returns_empty_list():
    assert XAdapter.extract_tweets({}) == []
    assert XAdapter.extract_tweets({"data": {}}) == []


def test_parse_jobs_from_llm_response():
    content = json.dumps({
        "jobs": [
            {
                "title": "Senior Python Engineer",
                "company": "未知",
                "salary": "150k-180k",
                "city": "远程",
                "contact": "DM",
                "source_url": "https://x.com/hiring_bot/status/1",
            }
        ]
    })

    jobs = llm.parse_jobs(content, channel="x", id_prefix="x")

    assert len(jobs) == 1
    job = jobs[0]
    assert job.channel == "x"
    assert job.external_id.startswith("x_")
    assert job.title == "Senior Python Engineer"
    assert "DM" in job.description
    assert job.url == "https://x.com/hiring_bot/status/1"


def test_parse_jobs_handles_malformed_json():
    assert llm.parse_jobs("not json", channel="x", id_prefix="x") == []


def test_parse_jobs_skips_items_without_title():
    content = json.dumps({"jobs": [{"company": "Acme"}]})
    assert llm.parse_jobs(content, channel="x", id_prefix="x") == []


def test_search_query_scopes_to_recent_days():
    adapter = XAdapter()
    q = adapter._search_query("java hiring", 90)
    assert q.startswith("java hiring since:")
    ranged = adapter._search_query("java hiring", since="2026-07-01", until="2026-07-08")
    assert ranged == "java hiring since:2026-07-01 until:2026-07-08"
    windows = adapter.date_windows(max_age_days=90, window_days=7)
    assert len(windows) == 13
    assert windows[0][1] is None
    dt = adapter.tweet_time("Mon Aug 11 00:00:00 +0000 2026")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 8
