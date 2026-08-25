import pytest

from app.infra.local_ai import LocalAiError, diagnose, engine_order, failure_message, run_sync


def test_engine_order_puts_preferred_first_then_the_rest():
    assert engine_order(None) == ["codex", "claude", "cursor-agent"]
    assert engine_order("claude")[0] == "claude"
    assert engine_order("claude") == ["claude", "codex", "cursor-agent"]
    assert engine_order("nope") == ["codex", "claude", "cursor-agent"]


def test_diagnose_names_the_actual_failure():
    assert diagnose("codex", timed_out=True, rc=None, stderr="", parsed=False) == "codex 超时"
    assert diagnose("claude", timed_out=False, rc=None, stderr="", parsed=False) == "claude 找不到"
    assert "断流" in diagnose(
        "codex", timed_out=False, rc=1,
        stderr="stream disconnected before completion", parsed=False,
    )
    assert diagnose("claude", timed_out=False, rc=0, stderr="", parsed=False) == (
        "claude 没吐出 JSON"
    )


def test_failure_message_when_no_cli():
    msg = failure_message(["claude", "codex", "cursor-agent"], [])
    assert "找不到 AI 订阅 CLI" in msg
    assert "codex" in msg


def test_failure_message_lists_each_engine():
    msg = failure_message([], ["codex 断流", "claude 超时"])
    assert msg.startswith("本机 AI 全失败：")
    assert "codex 断流" in msg
    assert "claude 超时" in msg


def test_run_sync_raises_clear_error_when_no_cli(monkeypatch):
    monkeypatch.setattr("app.infra.local_ai._resolve", lambda name: None)
    with pytest.raises(LocalAiError) as ei:
        run_sync("anything")
    assert "找不到 AI 订阅 CLI" in str(ei.value)
