from app.core import manual_job
from app.core import salary as salary_lib


def test_job_fields_and_sections():
    data = {
        "title": "Go 后端",
        "company": "Martax",
        "salary": "15k-20k·13薪",
        "salary_cny": "约 20–26万/年",
        "city": "",
        "is_remote": True,
        "experience": "3年",
        "education": "本科",
        "skills": ["Go", "Rust", ""],
        "district": "浦东",
        "industry": "互联网",
        "stage": "A轮",
        "scale": "50人",
        "welfare": ["双休", "远程"],
        "recruiter": "张三",
        "company_intro": "做 AI 工具",
        "sections": [
            {"title": "岗位信息", "body": "- 薪资 15k\n- 远程"},
            {"title": "要求", "body": "熟悉 Go"},
        ],
        "description": "",
        "fit_score": 72,
        "verdict": "值得一投",
        "one_liner": "栈能对上",
    }

    fields = manual_job.job_fields(data)
    assert fields["title"] == "Go 后端"
    assert fields["city"] == "远程"
    assert fields["skills"] == ["Go", "Rust"]
    assert fields["salary_cny"] == "约 20–26万/年"
    assert "## 岗位信息" in fields["description"]
    assert "熟悉 Go" in fields["description"]

    raw = manual_job.extras_for_raw(data)
    assert raw["areaDistrict"] == "浦东"
    assert raw["brandIndustry"] == "互联网"
    assert raw["welfareList"] == ["双休", "远程"]
    assert raw["sections"][0]["title"] == "岗位信息"
    assert raw["is_remote_hint"] is True

    match = manual_job.match_fields(data)
    assert match["fit_score"] == 72
    assert match["verdict"] == "值得一投"


def test_match_fields_fills_verdict_from_score():
    match = manual_job.match_fields({"fit_score": 90, "verdict": "瞎写"})
    assert match["verdict"] == "强烈推荐"
    assert match["fit_score"] == 90


def test_render_prompt_includes_resume_and_content():
    prompt = manual_job.render_prompt("招聘 Go 工程师", resume="我是 Java 后端")
    assert "我是 Java 后端" in prompt
    assert "招聘 Go 工程师" in prompt
    assert "fit_score" in prompt
    assert "sections" in prompt
    assert "salary_cny" in prompt


def test_split_markdown_jobs_by_hr():
    text = """
# Job A
Go 后端
---
# Job B
Java
----
# Job C
Python
"""
    parts = manual_job.split_markdown_jobs(text)
    assert len(parts) == 3
    assert "Job A" in parts[0]
    assert "Job B" in parts[1]
    assert "Job C" in parts[2]


def test_format_cny_from_usd():
    assert "万" in salary_lib.format_cny(100_000, 140_000)
    assert salary_lib.format_cny(0, 0) == ""
