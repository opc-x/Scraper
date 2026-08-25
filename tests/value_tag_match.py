from types import SimpleNamespace

from app.core.value_tag_match import catalog_text, parse_tag_ids, render_prompt


def test_parse_keeps_allowed_order_and_drops_junk():
    allowed = {1, 2, 7}
    assert parse_tag_ids({"tag_ids": [2, "1", 9, 2, "x"]}, allowed) == [2, 1]
    assert parse_tag_ids({"ids": [7]}, allowed) == [7]
    assert parse_tag_ids({"tag_ids": []}, allowed) == []
    assert parse_tag_ids(None, allowed) == []
    assert parse_tag_ids({"tag_ids": "1"}, allowed) == []


def test_catalog_lists_id_and_label():
    text = catalog_text([
        SimpleNamespace(id=1, label="加班", description="996 算减分"),
        SimpleNamespace(id=6, label="双休不打扰", description=""),
    ])
    assert "id=1 「加班」：996 算减分" in text
    assert "id=6 「双休不打扰」" in text


def test_prompt_keeps_user_note_and_job():
    prompt = render_prompt(catalog="- id=1 「加班」", job="标题：Go", note="感觉会加班")
    assert "感觉会加班" in prompt
    assert "标题：Go" in prompt
    assert "id=1 「加班」" in prompt
    assert "禁止发明新标签" in prompt
