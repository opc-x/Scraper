from app.core.resume_suggest import draft_analysis, draft_report_title, draft_suggestions


def test_analysis_follows_sop_and_flags_bare_bullets():
    md = "- 负责后端重构\n- 带 13 人"
    items = draft_analysis(md, sop_steps=[{"title": "挑刺", "body": "点到具体句子。"}])
    assert items[0]["title"] == "挑刺"
    assert any(i["title"] == "缺数字" and "负责后端重构" in i["quote"] for i in items)


def test_optimize_does_not_use_sop():
    md = "- 负责后端重构\n- 带 13 人"
    items = draft_suggestions(md, model="claude")
    assert any(i["title"] == "补数字" and "负责后端重构" in i["quote"] for i in items)
    assert all(i["title"] != "挑刺" for i in items)
    assert all(i["model"] == "claude" for i in items)


def test_empty_fallback():
    items = draft_suggestions("", model="codex")
    assert items[0]["title"] == "收一版"
    assert items[0]["model"] == "codex"


def test_report_title_puts_the_hole_first():
    title = draft_report_title(
        [
            {"title": "骨架", "quote": "", "body": "拆"},
            {"title": "缺数字", "quote": "性别：男", "body": ""},
            {"title": "缺数字", "quote": "意向岗位：Java 负责人", "body": ""},
            {"title": "缺数字", "quote": "意向城市：不限", "body": ""},
        ]
    )
    assert title.startswith("意向岗位")
    assert "没数字" in title


def test_optimize_from_brief_and_report():
    items = draft_suggestions(
        "- 带 13 人",
        model="cursor",
        brief="对准 Staff Java，把管理经历压短",
        findings=[{"title": "挑刺", "quote": "", "body": "空话太多"}],
    )
    assert items[0]["title"] == "按你写的改"
    assert any(i["title"] == "挑刺" for i in items)
    assert all(i["model"] == "cursor" for i in items)
