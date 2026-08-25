from app.core.sync_query import parse_sync_query


def test_parse_sync_query_full_expression():
    parsed = parse_sync_query("java or nodejs | remote or 远程 or 杭州 | 90")
    assert parsed["keyword_expr"] == {"op": "or", "terms": ["java", "nodejs"]}
    assert parsed["location_expr"] == {
        "op": "or",
        "terms": ["remote", "远程", "杭州"],
    }
    assert parsed["within_days"] == 90
    assert "jvm" in parsed["derived_keywords"]
    assert "hangzhou" in parsed["derived_locations"]


def test_parse_sync_query_defaults_days_and_accepts_full_width_pipe():
    parsed = parse_sync_query("java ｜ 杭州 ｜ nope")
    assert parsed["within_days"] == 90
    assert parsed["keyword_expr"]["terms"] == ["java"]


def test_parse_sync_query_caps_days():
    assert parse_sync_query("java||9999")["within_days"] == 365
