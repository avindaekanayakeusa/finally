"""Pydantic models for the chat endpoint and the LLM structured output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TradeInstruction(BaseModel):
    """A market order the LLM wants executed."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistInstruction(BaseModel):
    """A watchlist change the LLM wants applied."""

    ticker: str
    action: Literal["add", "remove"]


class LLMResponse(BaseModel):
    """Structured output the LLM must return. All fields are required."""

    message: str
    trades: list[TradeInstruction]
    watchlist_changes: list[WatchlistInstruction]


class ChatRequest(BaseModel):
    """Body of POST /api/chat."""

    message: str
