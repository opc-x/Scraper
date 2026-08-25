from app.core.ats_lookup import company_slugs, match_url, norm_title


def test_norm_title_strips_location_and_punct():
    assert norm_title("Software Engineer II, Growth (Remote)") == "software engineer ii growth"
    assert norm_title("Senior Java Engineer — Distributed Systems") == (
        "senior java engineer distributed systems"
    )


def test_company_slugs_skips_aggregators_and_keeps_glued_name():
    assert "andurilindustries" in company_slugs("Anduril Industries")
    assert company_slugs("NextHire") == []
    assert company_slugs("未知") == []


def test_match_url_requires_unique_exact_title():
    posts = [
        ("software engineer ii growth", "https://job-boards.greenhouse.io/amplitude/jobs/1"),
        ("staff software engineer", "https://job-boards.greenhouse.io/amplitude/jobs/2"),
    ]
    assert match_url("Software Engineer II, Growth", posts).endswith("/1")
    assert match_url("Engineer", posts) == ""
    dupes = [
        ("backend engineer", "https://example.com/a"),
        ("backend engineer", "https://example.com/b"),
    ]
    assert match_url("Backend Engineer", dupes) == ""
