"""Deterministic mock LLM used when LLM_MOCK=true (PLAN §9)."""

from __future__ import annotations

from .schema import LLMResponse, TradeInstruction, WatchlistInstruction


def mock_response(user_message: str) -> LLMResponse:
    """Return a canned response; first case-insensitive keyword match wins."""
    text = user_message.lower()
    if "buy" in text:
        return LLMResponse(
            message="Mock: buying 1 AAPL.",
            trades=[TradeInstruction(ticker="AAPL", side="buy", quantity=1)],
            watchlist_changes=[],
        )
    if "sell" in text:
        return LLMResponse(
            message="Mock: selling 1 AAPL.",
            trades=[TradeInstruction(ticker="AAPL", side="sell", quantity=1)],
            watchlist_changes=[],
        )
    if "watch" in text:
        return LLMResponse(
            message="Mock: adding PYPL to your watchlist.",
            trades=[],
            watchlist_changes=[WatchlistInstruction(ticker="PYPL", action="add")],
        )
    return LLMResponse(
        message="Mock: I am FinAlly, your AI trading assistant.",
        trades=[],
        watchlist_changes=[],
    )
