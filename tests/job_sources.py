from scripts.import_job_sources import source_account
from scripts.mine_x_remote_hiring_bulk import score


def test_x_prescreen_rewards_repeated_hiring_content():
    result = score(
        ["We're hiring a remote Python engineer. Apply now."] * 4,
        "Remote jobs and recruiting",
    )
    assert result["hiring_ratio"] == 1.0
    assert result["prescreen"] == 100


def test_source_account_maps_discovered_channel():
    account = source_account(
        {
            "username": "remote_python_jobs",
            "url": "https://t.me/remote_python_jobs",
            "job_score": 7,
            "description": "Remote Python roles",
        },
        "telegram",
    )
    assert account["handle"] == "remote_python_jobs"
    assert account["confidence"] == 96
    assert account["profile_url"].startswith("https://t.me/")
