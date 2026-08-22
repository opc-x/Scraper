from app.core.job_quality import evaluate_job


def job(**overrides):
    data = dict(
        title="Senior Java Backend Engineer", description="English-speaking global team. Build distributed Spring services " * 5,
        city="Remote", skills=["Java", "Spring"], salary="$150k-$180k",
        url="https://example.com/jobs/1",
    )
    data.update(overrides)
    return evaluate_job(**data)


def test_java_requires_remote():
    assert job().route == "java"
    assert not job(city="London", description="Build onsite Java Spring services " * 5).eligible


def test_agent_requires_remote_or_hangzhou_and_foreign_language():
    result = job(title="AI Agent Engineer", city="杭州", skills=["LangChain"],
                 description="国际化团队，使用英语办公。Build agentic workflows with LangChain " * 4)
    assert result.eligible
    assert result.route == "agent"
    assert not job(title="AI Agent Engineer", city="上海", skills=["LangChain"],
                   description="国际化团队，使用英语办公。Build agentic workflows " * 4).eligible


def test_rejects_generic_python_even_if_remote_and_high_paid():
    assert not job(title="Python Generalist", city="Remote", skills=["Python"],
                   description="English-speaking global team. Build FastAPI services " * 4,
                   salary="$150k-$170k").eligible


def test_requires_explicit_foreign_language_environment():
    assert not job(description="Build distributed Spring services " * 5).eligible


def test_rejects_roundups_and_missing_links():
    assert not job(title="Hey job seekers! 25 roles found").eligible
    assert not job(title="https://nomi.ai").eligible
    assert not job(title="Software Engineering").eligible
    assert not job(url="").eligible
