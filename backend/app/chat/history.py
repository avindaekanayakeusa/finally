"""Chat message persistence in the chat_messages table."""

from __future__ import annotations

import json
import sqlite3

from app.db import DEFAULT_USER, new_id, now_iso

HISTORY_LIMIT = 20


def load_history(conn: sqlite3.Connection, limit: int = HISTORY_LIMIT) -> list[dict]:
    """Last `limit` messages as LLM messages ({role, content}), oldest first."""
    rows = conn.execute(
        "SELECT role, content FROM ("
        "  SELECT role, content, created_at FROM chat_messages WHERE user_id = ?"
        "  ORDER BY created_at DESC LIMIT ?"
        ") ORDER BY created_at",
        (DEFAULT_USER, limit),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def save_message(
    conn: sqlite3.Connection, role: str, content: str, actions: dict | None = None
) -> None:
    """Append one message; actions are stored as JSON (null for user messages)."""
    with conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                DEFAULT_USER,
                role,
                content,
                json.dumps(actions) if actions is not None else None,
                now_iso(),
            ),
        )
