from app.core.job_derive import apply_derived
from app.core.job_origin import city_from_discord_text, origin_url, source_label, telegram_message_url
from app.db.schema import ScrapedJob


def test_source_label_discord_server_from_raw_and_url():
    assert source_label("discord", {"source_server": "CronJobs"}) == "CronJobs"
    assert source_label(
        "discord",
        url="https://discord.com/channels/1488674851345531057/1539435868031557724",
    ) == "CronJobs"
    assert source_label("telegram", {"source_channel": "remotejobs"}) == "remotejobs"
    assert source_label("boss", url="https://www.zhipin.com/job_detail/x.html") == ""


def test_origin_url_keeps_existing_http():
    assert origin_url("discord", url="https://discord.com/channels/1/2/3") == (
        "https://discord.com/channels/1/2/3"
    )


def test_origin_url_rebuilds_from_channel_id():
    assert origin_url("boss", "abc123") == "https://www.zhipin.com/job_detail/abc123.html"
    assert origin_url("v2ex", "v2ex_1234465") == "https://www.v2ex.com/t/1234465"
    assert origin_url("hackernews", "hn_49336502") == (
        "https://news.ycombinator.com/item?id=49336502"
    )
    assert origin_url("telegram", raw={"post": "remotejobs/88"}) == "https://t.me/remotejobs/88"
    assert origin_url("x", raw={"source_account": "hiring_bot"}) == "https://x.com/hiring_bot"
    assert origin_url("x_zh", raw={"source_account": "hr_zhang"}) == "https://x.com/hr_zhang"
    assert origin_url("eleduck", "0XfgRj") == "https://eleduck.com/posts/0XfgRj"


def test_origin_url_discord_falls_back_to_ats_link_in_description():
    url = origin_url(
        "discord",
        description="Apply at https://careers.dat.com/jobs/?gh_jid=6139594004 today",
    )
    assert url.startswith("https://careers.dat.com/")


def test_origin_url_discord_without_evidence_stays_empty():
    assert origin_url("discord", "dc_abc", url="", raw={"source_server": "CronJobs"}) == ""


def test_city_from_discord_jobsbot_salary_line():
    text = (
        "Amplitude — Software Engineer II, Growth | $146K – $200K\n"
        "$146K – $200K · San Francisco, CA · Mid-level\n"
        "TypeScript React Node.js"
    )
    assert city_from_discord_text(text) == "San Francisco, CA"


def test_city_from_discord_strips_skill_leak_and_generic_hybrid():
    leaked = "Remote • Portland, Oregon, USA Java Kubernetes Docker AWS"
    assert "Portland" in city_from_discord_text(leaked)
    assert city_from_discord_text("$98K – $98K · Hybrid · Senior") == ""
    assert city_from_discord_text("Work from home, fully remote team") == "远程"


def test_telegram_message_url_public_and_private():
    assert telegram_message_url("remotejobs", msg_id=88) == "https://t.me/remotejobs/88"
    assert telegram_message_url(entity_id=-1001234567890, msg_id=7) == (
        "https://t.me/c/1234567890/7"
    )


def test_apply_derived_fills_salary_cny_from_usd_salary():
    row = ScrapedJob(
        channel="discord",
        external_id="dc_1",
        title="Backend Engineer",
        company="Acme",
        salary="$146K – $200K",
        city="Remote",
        description="Remote English-speaking team building Java services " * 4,
        url="https://example.com/jobs/1",
    )
    apply_derived(row, approved_tags=[], manual_ids=set())
    assert row.salary_max_usd > 0
    assert row.salary_cny.startswith("约")
    assert "万" in row.salary_cny
