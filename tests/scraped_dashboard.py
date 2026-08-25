from datetime import datetime

from app.api.routes.scraped import KNOWN_CHANNELS, _apply_filters, _job_dict, _sort_index
from app.core.job_derive import apply_derived
from app.db.schema import ScrapedJob


def test_job_dict_reads_precomputed_derived_fields():
    """core_tags/regions/is_remote 现在是写时算好落库的列，_job_dict 只做取值，
    不再对 title/description 现场跑正则——这里用 apply_derived 模拟写路径先算好。"""
    row = ScrapedJob(
        id=1,
        channel="hackernews",
        external_id="hn_1",
        title="Agent Engineer",
        company="Acme",
        city="",
        skills=["Java", "Node.js"],
        description="Remote in EU building agentic systems with LangChain",
        url="https://example.com",
    )
    apply_derived(row, approved_tags=[], manual_ids=set())

    job = _job_dict(row)

    assert job["is_remote"] is True
    assert set(job["core_tags"]) >= {"java", "nodejs", "agent"}
    assert job["regions"] == ["EU"]


def test_known_channels_includes_boss():
    assert "boss" in KNOWN_CHANNELS


def _item(**overrides):
    base = {
        "channel": "x",
        "archived": False,
        "match_score": 80,
        "value_score": 50,
        "salary_hi": 0,
        "posted": datetime(2026, 1, 1),
        "tags": {"java"},
        "prefs": {"remote"},
        "is_remote": True,
        "value_matched": {"低英语要求"},
        "china_ok": True,
        "payload": {"id": 1},
    }
    base.update(overrides)
    return base


def test_apply_filters_hides_archived_and_keeps_tag():
    items = [
        _item(payload={"id": 1}),
        _item(archived=True, payload={"id": 2}),
        _item(tags={"python"}, payload={"id": 3}),
    ]
    kept = _apply_filters(
        items, channel="", tag="java", preference="", remote=None,
        min_score=None, include_archived=False,
    )
    assert [item["payload"]["id"] for item in kept] == [1]


def test_apply_filters_target_lens():
    items = [
        _item(payload={"id": 1}),
        _item(tags={"python"}, value_matched=set(), china_ok=False, is_remote=False, payload={"id": 2}),
        _item(value_matched=set(), payload={"id": 3}),
        _item(china_ok=False, payload={"id": 4}),
    ]
    kept = _apply_filters(
        items, channel="", tag="java", preference="", remote=True,
        min_score=None, include_archived=False,
        value_tag="低英语要求", china=True,
    )
    assert [item["payload"]["id"] for item in kept] == [1]


def test_refresh_archived_flags_patches_catalog():
    from app.api.routes import scraped as scraped_mod

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def all(self):
            return [("x", "a")]

    class FakeDB:
        def query(self, *_args):
            return FakeQuery()

    item = _item(channel="x", archived=False, payload={"id": 1, "external_id": "a"})
    scraped_mod._catalog_cache[90] = (0.0, [item])
    scraped_mod.refresh_archived_flags(FakeDB())
    assert item["archived"] is True
    scraped_mod._catalog_cache.clear()
    scraped_mod._cache.clear()


def test_sort_index_value_desc():
    items = [
        _item(value_score=40, match_score=90, payload={"id": 1}),
        _item(value_score=80, match_score=10, payload={"id": 2}),
    ]
    _sort_index(items, "value", True)
    assert [item["payload"]["id"] for item in items] == [2, 1]

