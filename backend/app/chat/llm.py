"""LLM call via LiteLLM with structured output, or the mock when LLM_MOCK=true."""

from __future__ import annotations

import os

import litellm

from .mock import mock_response
from .schema import LLMResponse

MODEL = "openai/gpt-5-mini"

SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant inside a simulated trading workstation.
The user trades a virtual portfolio with fake money; market orders fill instantly at the current price.

You can:
- Analyze portfolio composition, risk concentration, and P&L.
- Suggest trades with brief reasoning.
- Execute trades when the user asks or agrees, by listing them in "trades".
- Manage the watchlist proactively, by listing changes in "watchlist_changes".

Rules:
- Only tickers with a live price can be traded. To buy a symbol not on the watchlist,
  add it in "watchlist_changes" in the same response (watchlist changes run before trades).
- Quantities must be positive; fractional shares are allowed.
- Use empty arrays when there are no trades or watchlist changes.
- Be concise and data-driven. Always respond with valid JSON matching the schema."""


def is_mock() -> bool:
    """True when LLM_MOCK is set to 'true' (case-insensitive)."""
    return os.environ.get("LLM_MOCK", "").strip().lower() == "true"


async def get_llm_response(messages: list[dict], user_message: str) -> LLMResponse:
    """Return the structured response for the conversation.

    In mock mode the canned response is used and no API key is read.
    Raises on LLM/network errors or malformed output; the route maps that to 502.
    """
    if is_mock():
        return mock_response(user_message)
    response = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        response_format=LLMResponse,
        reasoning_effort="low",
    )
    return LLMResponse.model_validate_json(response.choices[0].message.content)
