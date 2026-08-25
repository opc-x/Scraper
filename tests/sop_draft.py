from app.core.sop_draft import fallback_plan, normalize_models, parse_plan, sop_title


def test_normalize_models_keeps_order_and_drops_junk():
    assert normalize_models(["Cursor", "nope", "claude", "cursor"]) == ["cursor", "claude"]
    assert normalize_models([]) == ["claude"]


def test_fallback_splits_brief_lines():
    plan = fallback_plan("只盯数字\n空话打回\n收口", ["codex", "claude"])
    assert len(plan["steps"]) == 3
    assert plan["steps"][0]["title"] == "只盯数字"
    assert plan["steps"][0]["from"] == "codex"
    assert plan["steps"][1]["from"] == "claude"


def test_parse_plan_uses_model_json():
    plan = parse_plan(
        {
            "description": "盯数字，空话打回。",
            "steps": [
                {"title": "补数字", "body": "每条要有量", "from": "codex"},
                {"title": "挑刺", "body": "点到句子", "from": "claude"},
            ],
        },
        brief="盯数字",
        models=["codex", "claude"],
    )
    assert plan["description"].startswith("盯数字")
    assert [s["title"] for s in plan["steps"]] == ["补数字", "挑刺"]


def test_sop_title_uses_first_clause():
    assert sop_title("只盯数字，空话打回", "盯岗位和数字。空话打回。", []) == "盯岗位和数字"
    assert sop_title("只盯数字", "这套 SOP 只审意向岗位匹配度", [{"title": "锁定岗位"}]) == "锁定岗位"


def test_parse_plan_falls_back_when_empty():
    plan = parse_plan({"steps": []}, brief="先拆骨架", models=["claude"])
    assert plan["steps"]
    assert plan["description"]
