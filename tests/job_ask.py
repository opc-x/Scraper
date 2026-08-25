from app.core.job_ask import job_context, normalize_reply, profile_to_reply, render_ask_prompt


def test_preference_prompt_keeps_user_text():
    prompt = render_ask_prompt(
        action="preference",
        context="Java 远程",
        resume="简历正文",
        message="少开会，能写 agent",
    )
    assert "偏好匹配" in prompt
    assert "少开会，能写 agent" in prompt
    assert "简历正文" in prompt


def test_unknown_action_rejected():
    try:
        render_ask_prompt(action="hack", context="x", resume="y", message="")
    except ValueError as exc:
        assert "unknown action" in str(exc)
    else:
        raise AssertionError("should reject unknown action")


def test_profile_to_reply_is_cached_score():
    reply = profile_to_reply({
        "fit_score": 72,
        "verdict": "可以投",
        "one_liner": "对口 Java",
        "stack_match": ["Java"],
        "stack_gap": ["K8s"],
    })
    assert reply["score"] == 72
    assert reply["cached"] is True
    assert reply["title"] == "简历匹配度"
    assert "Java" in reply["bullets"][1]


def test_normalize_reply_coerces_score():
    reply = normalize_reply({"title": "价值观评分", "summary": "稳", "score": "81", "bullets": ["少加班"]}, "values")
    assert reply["score"] == 81
    assert reply["bullets"] == ["少加班"]


def test_job_context_includes_title():
    text = job_context(
        title="高级 Java",
        company="数字浙江",
        salary="30-50K",
        city="杭州",
        skills=["Java"],
        channel="boss",
        description="岗位职责：写代码",
    )
    assert "高级 Java" in text
    assert "写代码" in text
