"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def event_loop_policy():
    """Use the default event loop policy for all async tests."""
    import asyncio

    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Fresh, initialized SQLite database in a temp dir; yields an open connection."""
    from app.db import get_connection, init_db

    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "test.db"))
    init_db()
    conn = get_connection()
    yield conn
    conn.close()
