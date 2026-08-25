from app.core import job_rules, match_score
from app.core.quality_inspect import inspect_text, should_block


def setup_function():
    job_rules.invalidate_cache()


def test_compose_weights_rule_over_llm():
    b = match_score.compose(
        95,
        title="Hiring someone",
        description="We are a nice company looking for people to join.",
        city="Beijing",
        skills=[],
    )
    assert b.llm_score == 95
    assert b.rule_score < 50
    assert b.score < 70


def test_compose_caps_wrong_role():
    b = match_score.compose(
        90,
        title="Frontend React Designer",
        description="UI design and marketing site",
        city="Remote",
        skills=["Figma"],
    )
    assert b.score <= 35
    assert any("错岗" in c or "35" in c for c in b.caps)


def test_compose_java_remote_raises_rule():
    b = match_score.compose(
        70,
        title="Java Backend Engineer",
        description="Remote Java Spring Kafka Elasticsearch distributed systems",
        city="远程",
        skills=["Java", "Kafka"],
    )
    assert b.rule_score >= 60
    assert b.score >= 60
    assert b.verdict in {"值得一投", "强烈推荐"}


def test_inspect_block_incomplete_not_suspect_only():
    findings = inspect_text(title="", description="短")
    assert should_block(findings)
    assert any(f.severity == "block" for f in findings)


def test_inspect_nav_noise_is_suspect_not_block():
    desc = (
        "我们招 Java 后端，远程办公，负责分布式系统。"
        "Privacy Policy Cookie Sign in Log in 热门推荐 相关职位"
    )
    findings = inspect_text(title="Java 后端", description=desc)
    assert not should_block(findings)
    assert any(f.kind == "nav_noise" and f.severity == "suspect" for f in findings)


def test_seed_rules_have_expected_categories():
    cats = {r.category for r in job_rules.all_rules(force=True)}
    assert "match_stack" in cats
    assert "quality_block" in cats
    assert "recall" in cats
    assert job_rules.config_value("rule_weight_pct") == 65
