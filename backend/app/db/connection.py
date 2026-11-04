"""SQLite connection handling, schema creation and seeding."""

from __future__ import annotations

import os
import sqlite3
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCHEMA_PATH = BACKEND_DIR / "db" / "schema.sql"
DEFAULT_DB_PATH = BACKEND_DIR.parent / "db" / "finally.db"

DEFAULT_USER = "default"
DEFAULT_CASH = 10000.0
DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def db_path() -> Path:
    """Database file path: FINALLY_DB_PATH if set, else ``<root>/db/finally.db``."""
    return Path(os.environ.get("FINALLY_DB_PATH") or DEFAULT_DB_PATH)


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string ending in ``Z``."""
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_id() -> str:
    """New random UUID string for a primary key."""
    return str(uuid.uuid4())


def get_connection() -> sqlite3.Connection:
    """Open a connection with dict-like rows, usable across threads."""
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency yielding a connection that is closed afterwards."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if missing and seed the default user and watchlist once."""
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        _seed(conn)
    finally:
        conn.close()


def _seed(conn: sqlite3.Connection) -> None:
    """Insert the default user and watchlist if the user does not exist yet."""
    if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (DEFAULT_USER,)).fetchone():
        return
    with conn:
        conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER, DEFAULT_CASH, now_iso()),
        )
        conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            [(new_id(), DEFAULT_USER, t, now_iso()) for t in DEFAULT_TICKERS],
        )
