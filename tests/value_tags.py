from datetime import datetime, timedelta
from types import SimpleNamespace

from app.core.job_derive import _gap_tags, _lens_lang, evaluate_ingest_gate, java_in_title, matches_target_lens
from app.core.value_tags import score_job_with


def _tag(**kwargs):
    defaults = dict(
        id=1, label="低英语要求", category="价值观", polarity=1, weight=20,
        pattern=r"[\u4e00-\u9fff]|mandarin|中文办公",
        description="", salary_below_usd=None, pinned=True,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_pinned_bonus_tag_emits_green_on_hit_and_red_on_miss():
    tag = _tag()
    _, hits = score_job_with(
        [tag], set(), title="Java 远程", description="中文办公", city="远程", skills=["java"],
    )
    assert hits[0]["label"] == "低英语要求"
    assert hits[0]["matched"] is True

    _, misses = score_job_with(
        [tag], set(), title="Senior Java", description="Fluent English required",
        city="Remote", skills=["java"],
    )
    assert misses[0]["matched"] is False
    assert len(misses) == 1

    _, english = score_job_with(
        [tag], set(), title="Remote Java Backend", description="Worldwide remote, no language listed",
        city="Remote", skills=["java"], low_english_mode="en",
    )
    assert english[0]["matched"] is True

    _, zh_ok = score_job_with(
        [tag], set(), title="Remote Java Backend", description="Worldwide remote, no language listed",
        city="Remote", skills=["java"], low_english_mode="zh",
    )
    assert zh_ok[0]["matched"] is True


def test_unpinned_bonus_tag_hidden_when_missed():
    tag = _tag(pinned=False, label="双休", pattern=r"双休")
    _, hits = score_job_with(
        [tag], set(), title="Java", description="English only", city="Remote", skills=[],
    )
    assert hits == []


def test_neutral_tag_is_emitted_without_changing_score():
    tag = _tag(polarity=0, pinned=False, label="外包", pattern=r"外包")
    score, hits = score_job_with(
        [tag], set(), title="Java 外包工程师", description="", city="杭州", skills=["java"],
    )
    assert score == 50
    assert hits[0]["label"] == "外包"
    assert hits[0]["matched"] is True


def test_ai_assignment_keeps_its_source():
    tag = _tag(pinned=False, label="少开会", pattern=r"绝不命中")
    _, hits = score_job_with(
        [tag], {tag.id}, title="Java", description="", city="杭州", skills=["java"],
        assignment_sources={tag.id: "ai_assist"},
    )
    assert hits[0]["source"] == "ai_assist"
    assert hits[0]["auto"] is False


def test_chinese_city_does_not_count_as_low_english():
    tag = _tag()
    _, hits = score_job_with(
        [tag], set(), title="Senior Java", description="Fluent English required",
        city="远程", skills=["java"],
    )
    assert hits[0]["matched"] is False


def test_china_eligible_requires_remote_without_geo_lock():
    from app.core.job_derive import china_eligible
    assert china_eligible(is_remote=True, description="Fully remote worldwide") is True
    assert china_eligible(is_remote=False, description="远程居家") is False
    assert china_eligible(is_remote=True, description="Must be authorized to work in the US") is False
    assert china_eligible(is_remote=True, city="Chicago", description="Remote Java") is False
    assert china_eligible(is_remote=True, city="Los Angeles", description="Fully remote Java") is False
    assert china_eligible(is_remote=True, city="Philadelphia, PA", description="Remote") is False
    assert china_eligible(is_remote=True, city="Remote", description="Non-US Countries Only") is True


def _fresh(**kwargs):
    row = dict(
        skills=["java"], core_tags=["java"], is_remote=True,
        value_tags=[{"label": "低英语要求", "matched": True}],
        posted_at=datetime.utcnow() - timedelta(days=10),
    )
    row.update(kwargs)
    return SimpleNamespace(**row)


def _patch_gate_80(monkeypatch):
    from app.core import job_rules as rules

    monkeypatch.setattr(rules, "rule_by_key", lambda *_a, **_k: SimpleNamespace(weight=80, enabled=True))
    monkeypatch.setattr(rules, "by_category", lambda *_a, **_k: [
        SimpleNamespace(key="java", weight=25, enabled=True),
        SimpleNamespace(key="remote", weight=25, enabled=True),
        SimpleNamespace(key="wfh", weight=25, enabled=True),
        SimpleNamespace(key="low_english", weight=25, enabled=True),
        SimpleNamespace(key="fresh", weight=25, enabled=True),
        SimpleNamespace(key="china", weight=25, enabled=True),
    ])


def test_java_in_title_is_simple_word():
    assert java_in_title("Java 开发工程师-远程办公") is True
    assert java_in_title("远程办公java") is True
    assert java_in_title("Remote Java Backend") is True
    assert java_in_title("Frontend Developer") is False
    assert java_in_title("Good JavaScript developer") is False
    assert java_in_title("诚招全栈 go 后端方向(接受 Java 转 go）") is False
    assert java_in_title("Backend Engineer") is False
    assert java_in_title("Flutter / Vue / Python / Java / AI 工程师") is False


def test_ingest_gate_accepts_java_skill_for_generic_title_but_not_conflicting_stack(monkeypatch):
    _patch_gate_80(monkeypatch)
    generic = _fresh(
        channel="remoteok",
        title="Backend Engineer",
        description="Worldwide remote, anywhere. Spring Boot services.",
        city="Remote",
        skills=["java", "spring"],
    )
    conflicting = _fresh(
        channel="remoteok",
        title="Python Developer",
        description="Worldwide remote, anywhere.",
        city="Remote",
        skills=["java", "python"],
    )
    assert matches_target_lens(generic) is True
    assert matches_target_lens(conflicting) is False


def test_lens_lang_maps_channel_to_mode():
    assert _lens_lang("boss") == "zh"
    assert _lens_lang("v2ex") == "zh"
    assert _lens_lang("eleduck") == "zh"
    assert _lens_lang("discord") == "en"
    assert _lens_lang("x") == "en"
    assert _lens_lang("x_zh") == "zh"
    assert _lens_lang("hackernews") == "en"
    assert _lens_lang("remoteok") == "en"
    assert _lens_lang("weworkremotely") == "en"
    assert _lens_lang("telegram") == "both"
    assert _lens_lang("") == "both"


def test_target_lens_keeps_java_remote_low_english_wfh(monkeypatch):
    _patch_gate_80(monkeypatch)
    keep = _fresh(
        channel="boss",
        title="Java 开发工程师-远程办公", description="中文办公 接受居家办公", city="上海",
    )
    assert matches_target_lens(keep) is True
    boss_en = _fresh(
        channel="boss",
        title="Remote Java Backend", description="Worldwide remote", city="Remote",
    )
    assert matches_target_lens(boss_en) is True
    ru = _fresh(
        channel="telegram",
        title="Java Backend Developer (Sber)",
        description="Удалённо по РФ. Java Core, Spring Boot, Kafka.",
        city="Удалённо",
    )
    assert matches_target_lens(ru) is True
    duck = _fresh(
        channel="eleduck",
        title="Remote Java Backend Developer",
        description="Worldwide remote Spring Boot",
        city="Remote",
    )
    assert matches_target_lens(duck) is True


def test_target_lens_matches_cjk_java_title(monkeypatch):
    _patch_gate_80(monkeypatch)
    row = _fresh(
        channel="v2ex",
        title="远程办公java", description="中文办公 接受居家办公", city="上海",
    )
    assert matches_target_lens(row) is True


def test_target_lens_keeps_english_hn_java_in_body(monkeypatch):
    _patch_gate_80(monkeypatch)
    row = _fresh(
        channel="hackernews",
        title="Backend Engineer | REMOTE (Worldwide)",
        description="We need a Java / Spring Boot engineer. Fully remote, anywhere.",
        city="Remote",
        skills=["java"],
    )
    assert matches_target_lens(row) is True
    row = _fresh(
        channel="discord",
        title="Hiring: Remote Java Backend Developer (Non-US Countries Only)",
        description="Worldwide remote. Spring Boot, Kafka.",
        city="Remote",
    )
    assert matches_target_lens(row) is True
    tg_en = _fresh(
        channel="telegram",
        title="Remote Java Developer",
        description="Fully remote, anywhere.",
        city="Remote",
    )
    assert matches_target_lens(tg_en) is True
    tg_zh = _fresh(
        channel="telegram",
        title="Java 开发工程师-远程办公",
        description="中文办公 接受居家办公",
        city="远程",
    )
    assert matches_target_lens(tg_zh) is True
    old = _fresh(
        channel="hackernews",
        title="Hiring: Remote Java Backend Developer (Non-US Countries Only)",
        description="Worldwide remote. Spring Boot, Kafka.",
        city="Remote",
        posted_at=datetime.utcnow() - timedelta(days=91),
    )
    assert matches_target_lens(old) is True
    hard = _fresh(
        channel="discord",
        title="Remote Java Backend",
        description="Fluent English required. Worldwide remote.",
        city="Remote",
    )
    assert matches_target_lens(hard) is True
    py = _fresh(
        channel="remoteok",
        title="Python Developer",
        description="We use Django and Postgres. Fully remote, anywhere.",
        city="Remote",
        skills=["java", "python"],
    )
    assert matches_target_lens(py) is False
    js = _fresh(
        channel="weworkremotely",
        title="Frontend Developer",
        description="Good JavaScript developer. React + Node. 100% remote.",
        city="Remote",
    )
    assert matches_target_lens(js) is False
    java_script = _fresh(
        channel="weworkremotely",
        title="Web Developer",
        description="Strong HTML, CSS, PHP and Java Script skills. 100% remote.",
        city="Remote",
        skills=[],
    )
    assert matches_target_lens(java_script) is False
    java_in_jd = _fresh(
        channel="weworkremotely",
        title="Backend Engineer",
        description="Build services with Java and Spring Boot. 100% remote, worldwide.",
        city="Remote",
    )
    assert matches_target_lens(java_in_jd) is True
    fe_java = _fresh(
        channel="remoteok",
        title="Front End Full Stack Developer",
        description="Front-End / Full Stack Developer (React + Java) Backend: Java, Spring",
        city="Philadelphia, PA",
    )
    assert matches_target_lens(fe_java) is False


def test_target_lens_drops_interview_only_and_java_mention(monkeypatch):
    _patch_gate_80(monkeypatch)
    interview = _fresh(
        channel="boss",
        title="Java开发（远程面试）", description="不接受居家办公", city="上海",
    )
    pivot = _fresh(
        channel="v2ex",
        title="诚招全栈 go 后端方向(接受 Java 转 go）", description="线下或远程办公", city="远程",
        skills=["go"],
    )
    english = _fresh(
        channel="boss",
        title="远程 Java 工程师", description="中文办公", city="远程",
        value_tags=[
            {"label": "低英语要求", "matched": True},
            {"label": "英语环境", "matched": True},
        ],
    )
    assert matches_target_lens(interview) is False
    assert matches_target_lens(pivot) is False
    assert matches_target_lens(english) is True


def test_target_lens_keeps_paren_remote(monkeypatch):
    _patch_gate_80(monkeypatch)
    row = _fresh(
        channel="boss",
        title="Java理财方向（远程）", description="Java · Spring · 年终奖", city="杭州",
    )
    assert matches_target_lens(row) is True


def test_target_lens_keeps_80pct_and_tags_gaps(monkeypatch):
    _patch_gate_80(monkeypatch)
    la = _fresh(
        channel="remoteok",
        title="Java Developer",
        description="Fully remote Java Spring Boot",
        city="Los Angeles",
    )
    assert matches_target_lens(la) is True
    _, la_detail = evaluate_ingest_gate(
        title=la.title, description=la.description, city=la.city,
        is_remote=True, skills=la.skills, channel=la.channel,
        posted_at=la.posted_at, force=True,
    )
    assert la_detail["ratio_pct"] == 80
    assert {t["label"] for t in _gap_tags(la_detail["signals"])} == {"缺大陆可投"}

    hard = _fresh(
        channel="discord",
        title="Remote Java Backend",
        description="Fluent English required. Worldwide remote.",
        city="Remote",
    )
    assert matches_target_lens(hard) is True
    _, hard_detail = evaluate_ingest_gate(
        title=hard.title, description=hard.description, city=hard.city,
        is_remote=True, skills=hard.skills, channel=hard.channel,
        posted_at=hard.posted_at, force=True,
    )
    assert {t["label"] for t in _gap_tags(hard_detail["signals"])} == {"缺低英语"}

    old = _fresh(
        channel="hackernews",
        title="Hiring: Remote Java Backend Developer (Non-US Countries Only)",
        description="Worldwide remote. Spring Boot, Kafka.",
        city="Remote",
        posted_at=datetime.utcnow() - timedelta(days=91),
    )
    assert matches_target_lens(old) is True
    _, old_detail = evaluate_ingest_gate(
        title=old.title, description=old.description, city=old.city,
        is_remote=True, skills=old.skills, channel=old.channel,
        posted_at=old.posted_at, force=True,
    )
    assert {t["label"] for t in _gap_tags(old_detail["signals"])} == {"缺90天内"}


def test_ingest_gate_signals_follow_channel_lang(monkeypatch):
    from types import SimpleNamespace as NS

    from app.core import job_rules as rules

    monkeypatch.setattr(rules, "rule_by_key", lambda *_a, **_k: NS(weight=75, enabled=True))
    monkeypatch.setattr(rules, "by_category", lambda *_a, **_k: [
        NS(key="java", weight=25, enabled=True),
        NS(key="remote", weight=25, enabled=True),
        NS(key="wfh", weight=25, enabled=True),
        NS(key="low_english", weight=25, enabled=True),
    ])
    kwargs = dict(
        title="Remote Java Backend Engineer",
        description="Worldwide remote, anywhere.",
        city="Remote",
        is_remote=True,
        skills=["java"],
    )
    _, zh = evaluate_ingest_gate(**kwargs, channel="boss")
    assert zh["signals"]["java"] is True
    assert zh["signals"]["wfh"] is True
    assert zh["signals"]["low_english"] is True
    _, en = evaluate_ingest_gate(**kwargs, channel="hackernews")
    assert en["signals"]["java"] is True
    assert en["signals"]["wfh"] is True
    assert en["signals"]["low_english"] is True
    zh_job = dict(
        title="Java 开发工程师-远程办公",
        description="中文办公 接受居家办公",
        city="上海",
        is_remote=True,
        skills=["java"],
    )
    _, tg = evaluate_ingest_gate(**zh_job, channel="telegram")
    assert tg["signals"]["java"] is True
    assert tg["signals"]["wfh"] is True
    assert tg["signals"]["low_english"] is True


def test_x_zh_ingest_gate_uses_60pct(monkeypatch):
    from app.core import job_rules as rules

    def by_key(_cat, key):
        if key == "threshold_pct_x_zh":
            return SimpleNamespace(weight=60, enabled=True)
        return SimpleNamespace(weight=80, enabled=True)

    monkeypatch.setattr(rules, "rule_by_key", by_key)
    monkeypatch.setattr(rules, "by_category", lambda *_a, **_k: [
        SimpleNamespace(key=k, weight=25, enabled=True)
        for k in ("java", "remote", "wfh", "low_english", "fresh", "china")
    ])
    kwargs = dict(
        title="后端开发",
        description=(
            "急招 Java。Fully remote, work from home. "
            "Fluent English required. Must be located in the US."
        ),
        city="Remote",
        is_remote=True,
        skills=["java"],
        posted_at=datetime.utcnow() - timedelta(days=10),
        force=True,
    )
    ok_zh, zh = evaluate_ingest_gate(**kwargs, channel="x_zh")
    ok_en, en = evaluate_ingest_gate(**kwargs, channel="x")
    assert zh["signals"]["java"] is True
    assert zh["ratio_pct"] == 60
    assert zh["threshold_pct"] == 60
    assert ok_zh is True
    assert en["threshold_pct"] == 80
    assert ok_en is False


def test_x_zh_hangzhou_onsite_passes_at_60(monkeypatch):
    from app.core import job_rules as rules

    def by_key(_cat, key):
        if key == "threshold_pct_x_zh":
            return SimpleNamespace(weight=60, enabled=True)
        return SimpleNamespace(weight=80, enabled=True)

    monkeypatch.setattr(rules, "rule_by_key", by_key)
    monkeypatch.setattr(rules, "by_category", lambda *_a, **_k: [
        SimpleNamespace(key=k, weight=25, enabled=True)
        for k in ("java", "remote", "wfh", "low_english", "fresh", "china")
    ])
    ok, detail = evaluate_ingest_gate(
        title="Java开发",
        description="急招Java开发工程师，杭州坐班。",
        city="杭州",
        is_remote=False,
        skills=["java"],
        posted_at=datetime.utcnow() - timedelta(days=10),
        force=True,
        channel="x_zh",
    )
    assert detail["signals"]["java"] is True
    assert detail["signals"]["remote"] is False
    assert detail["signals"]["wfh"] is False
    assert detail["signals"]["china"] is True
    assert detail["ratio_pct"] == 60
    assert ok is True
