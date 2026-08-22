from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.adapters.eleduck import API_ROOT, EleduckAdapter, _plain_text, _to_job


def test_to_job_preserves_source_facts():
    post = {
        "id": "abc123",
        "title": "Java 后端工程师",
        "full_title": "【远程】Java 后端工程师 20K-30K",
        "published_at": "2026-08-01T10:00:00+08:00",
        "content": "<p>Spring Boot，英文团队，<strong>全职远程</strong></p>",
        "status": "published",
        "category": {"code": "jd"},
        "user": {"nickname": "招聘方"},
        "tags": [
            {"name": "开发", "tag_group": {"code": "skill_type"}},
            {"name": "全职远程", "tag_group": {"code": "job_type"}},
        ],
    }
    job = _to_job(post)
    assert job.external_id == "abc123"
    assert job.url == "https://eleduck.com/posts/abc123"
    assert job.salary == "20K-30K"
    assert job.city == "远程"
    assert job.raw["posted_at"] == post["published_at"]
    assert job.raw["is_remote"] is True
    assert "<p>" not in job.description


def test_plain_text():
    assert _plain_text("<p>Java &amp; Spring</p><p>Remote</p>") == "Java & Spring\nRemote"


@pytest.mark.asyncio
async def test_recent_window_minimum_and_details():
    now = datetime.now(timezone.utc)
    recent = (now - timedelta(days=2)).isoformat()
    old = (now - timedelta(days=100)).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jobs_channel/posts"):
            page = int(request.url.params["page"])
            if page == 1:
                posts = [
                    {
                        "id": "java1",
                        "title": "Java 开发",
                        "summary": "Spring Remote",
                        "published_at": recent,
                        "closed": False,
                        "category": {"code": "jd"},
                        "tags": [],
                    }
                ]
            else:
                posts = [
                    {
                        "id": "old1",
                        "title": "Java 开发",
                        "summary": "Spring",
                        "published_at": old,
                        "closed": False,
                        "category": {"code": "jd"},
                        "tags": [],
                    }
                ]
            return httpx.Response(200, json={"posts": posts, "pager": {"pages": 2}})
        assert str(request.url) == f"{API_ROOT}/posts/java1"
        return httpx.Response(
            200,
            json={
                "post": {
                    "id": "java1",
                    "title": "Java 开发",
                    "content": "<p>Spring Boot，全职远程</p>",
                    "published_at": recent,
                    "category": {"code": "jd"},
                    "tags": [],
                    "user": {"nickname": "公司"},
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = EleduckAdapter(client=client)
    jobs = await adapter.fetch_recent(max_age_days=90, min_jobs=1, fetch_details=True)
    await client.aclose()
    assert [job.external_id for job in jobs] == ["java1"]
    assert "Spring Boot" in jobs[0].description


@pytest.mark.asyncio
async def test_minimum_is_enforced():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"posts": [], "pager": {"pages": 1}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = EleduckAdapter(client=client)
    with pytest.raises(RuntimeError, match="低于要求"):
        await adapter.fetch_recent(min_jobs=150)
    await client.aclose()
