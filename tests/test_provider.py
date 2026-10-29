"""AnthropicCompleter against a stand-in SDK (no network, no API key)."""
import sys
import types

import pytest

from muffin.providers import AnthropicCompleter


class _Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Msg:
    def __init__(self, blocks, stop_reason="end_turn"):
        self.content = blocks
        self.stop_reason = stop_reason


@pytest.fixture
def fake_sdk(monkeypatch):
    calls = {"init": None, "create": []}
    reply = {"msg": _Msg([_Block("text", '{"action": null}')])}

    class _Messages:
        def create(self, **kwargs):
            calls["create"].append(kwargs)
            return reply["msg"]

    class _Client:
        def __init__(self, **kwargs):
            calls["init"] = kwargs
            self.messages = _Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return calls, reply


def test_passes_timeout_and_retries_to_the_sdk(fake_sdk):
    calls, _ = fake_sdk
    AnthropicCompleter(timeout=5, max_retries=4)
    assert calls["init"] == {"timeout": 5.0, "max_retries": 4}


def test_default_max_tokens_is_not_tiny(fake_sdk):
    calls, _ = fake_sdk
    AnthropicCompleter()("sys", "hi")
    assert calls["create"][0]["max_tokens"] >= 1024


def test_sends_system_and_prompt_and_joins_text_blocks(fake_sdk):
    calls, reply = fake_sdk
    reply["msg"] = _Msg([_Block("text", "a"), _Block("tool_use"), _Block("text", "b")])
    assert AnthropicCompleter(model="m")("SYS", "PROMPT") == "ab"
    sent = calls["create"][0]
    assert sent["model"] == "m"
    assert sent["system"] == "SYS"
    assert sent["messages"] == [{"role": "user", "content": "PROMPT"}]


def test_truncated_reply_raises_instead_of_returning_half_json(fake_sdk):
    _, reply = fake_sdk
    reply["msg"] = _Msg([_Block("text", '{"action": "send_em')], stop_reason="max_tokens")
    with pytest.raises(ValueError, match="max_tokens"):
        AnthropicCompleter()("sys", "hi")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tokens": 0},
        {"max_tokens": True},
        {"max_tokens": 1.5},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("nan")},
        {"timeout": True},
        {"max_retries": -1},
        {"max_retries": True},
    ],
)
def test_rejects_invalid_settings(fake_sdk, kwargs):
    with pytest.raises(ValueError):
        AnthropicCompleter(**kwargs)


def test_missing_sdk_gives_a_helpful_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` fail
    with pytest.raises(ImportError, match="muffin-ai\\[llm\\]"):
        AnthropicCompleter()
