"""POST /api/chat: LLM turn with auto-executed actions."""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db
from app.market import MarketDataSource, PriceCache

from .context import build_context
from .execute import execute_actions
from .history import load_history, save_message
from .llm import SYSTEM_PROMPT, get_llm_response
from .schema import ChatRequest

logger = logging.getLogger(__name__)


def build_messages(context: str, history: list[dict], user_message: str) -> list[dict]:
    """System prompt, portfolio context, prior conversation, then the new message."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": context},
        *history,
        {"role": "user", "content": user_message},
    ]


def create_chat_router(cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Router exposing POST /api/chat bound to the shared cache and market source."""
    router = APIRouter(prefix="/api")

    @router.post("/chat")
    async def chat(req: ChatRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
        messages = build_messages(build_context(conn, cache), load_history(conn), req.message)
        try:
            response = await get_llm_response(messages, req.message)
        except Exception as e:
            logger.exception("LLM call failed")
            raise HTTPException(status_code=502, detail=f"LLM request failed: {e}") from e
        actions = await execute_actions(conn, cache, source, response)
        save_message(conn, "user", req.message)
        save_message(conn, "assistant", response.message, actions)
        return {"message": response.message, "actions": actions}

    return router
