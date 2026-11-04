"""LLM call: mock switch, LiteLLM arguments, structured output parsing."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.chat import llm
from app.chat.schema import LLMResponse


def fake_completion(content: str, calls: list):
    """Stand-in for litellm.acompletion returning `content` as the message."""

    async def _acompletion(**kwargs):
        calls.append(kwargs)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    return _acompletion


async def test_mock_mode_skips_litellm(mock_mode, monkeypatch):
    calls = []
    monkeypatch.setattr(llm.litellm, "acompletion", fake_completion("{}", calls))
    r = await llm.get_llm_response([], "hi")
    assert r.message.startswith("Mock:")
    assert calls == []


async def test_real_call_arguments_and_parsing(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    calls = []
    content = '{"message": "ok", "trades": [{"ticker": "NVDA", "side": "buy", "quantity": 2.5}], "watchlist_changes": []}'
    monkeypatch.setattr(llm.litellm, "acompletion", fake_completion(content, calls))
    messages = [{"role": "user", "content": "buy nvda"}]
    r = await llm.get_llm_response(messages, "buy nvda")
    assert r.trades[0].ticker == "NVDA" and r.trades[0].quantity == 2.5
    kwargs = calls[0]
    assert kwargs["model"] == "openai/gpt-5-mini"
    assert kwargs["response_format"] is LLMResponse
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["messages"] == messages
    assert "temperature" not in kwargs and "top_p" not in kwargs


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"message": "missing fields"}',
        '{"message": "x", "trades": [{"ticker": "A", "side": "hold", "quantity": 1}], "watchlist_changes": []}',
    ],
)
async def test_malformed_output_raises(monkeypatch, content):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setattr(llm.litellm, "acompletion", fake_completion(content, []))
    with pytest.raises(ValidationError):
        await llm.get_llm_response([], "x")


def test_schema_marks_all_fields_required():
    assert set(LLMResponse.model_json_schema()["required"]) == {
        "message",
        "trades",
        "watchlist_changes",
    }
