from app.api.routes.scraped import KNOWN_CHANNELS, _job_dict
from app.db.schema import ScrapedJob


def test_job_dict_adds_core_remote_and_region_tags():
    row = ScrapedJob(
        id=1,
        channel="hackernews",
        external_id="hn_1",
        title="Agent Engineer",
        company="Acme",
        city="",
        skills=["Java", "Node.js"],
        description="Remote in EU building agentic systems with LangChain",
        url="https://example.com",
    )

    job = _job_dict(row)

    assert job["is_remote"] is True
    assert set(job["core_tags"]) >= {"java", "nodejs", "agent"}
    assert job["regions"] == ["EU"]


def test_known_channels_includes_boss():
    assert "boss" in KNOWN_CHANNELS

