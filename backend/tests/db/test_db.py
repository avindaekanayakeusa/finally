"""Tests for schema init, seeding, ticker validation and tracking."""

import pytest

from app.db import (
    DEFAULT_TICKERS,
    get_tracked_tickers,
    init_db,
    sync_tracked_tickers,
    validate_ticker,
)


def test_seed_creates_default_user_and_watchlist(db_conn):
    user = db_conn.execute("SELECT * FROM users_profile").fetchall()
    assert [(u["id"], u["cash_balance"]) for u in user] == [("default", 10000.0)]
    rows = db_conn.execute("SELECT ticker FROM watchlist ORDER BY added_at").fetchall()
    assert [r["ticker"] for r in rows] == DEFAULT_TICKERS


def test_init_db_is_idempotent(db_conn):
    db_conn.execute("DELETE FROM watchlist WHERE ticker = 'AAPL'")
    db_conn.commit()
    init_db()
    assert db_conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0] == 1
    assert db_conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0] == 9


def test_all_tables_exist(db_conn):
    names = {r[0] for r in db_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users_profile", "watchlist", "positions", "trades",
            "portfolio_snapshots", "chat_messages"} <= names


@pytest.mark.parametrize("raw,expected", [("aapl", "AAPL"), (" V ", "V"), ("GOOGL", "GOOGL")])
def test_validate_ticker_accepts(raw, expected):
    assert validate_ticker(raw) == expected


@pytest.mark.parametrize("raw", ["", "TOOLONG", "BRK.B", "A1", "12"])
def test_validate_ticker_rejects(raw):
    with pytest.raises(ValueError):
        validate_ticker(raw)


def _add_position(conn, ticker):
    conn.execute(
        "INSERT INTO positions (id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, 1, 100, '2030-01-01T00:00:00Z')",
        (ticker, ticker),
    )
    conn.commit()


def test_tracked_tickers_is_union(db_conn):
    _add_position(db_conn, "PYPL")
    _add_position(db_conn, "AAPL")
    assert get_tracked_tickers(db_conn) == DEFAULT_TICKERS + ["PYPL"]


class FakeSource:
    """Minimal in-memory stand-in for a MarketDataSource."""

    def __init__(self, tickers):
        self.tickers = list(tickers)

    async def add_ticker(self, ticker):
        if ticker not in self.tickers:
            self.tickers.append(ticker)

    async def remove_ticker(self, ticker):
        if ticker in self.tickers:
            self.tickers.remove(ticker)

    def get_tickers(self):
        return list(self.tickers)


async def test_sync_tracked_tickers(db_conn):
    _add_position(db_conn, "PYPL")
    source = FakeSource(["AAPL", "ZZZ"])
    await sync_tracked_tickers(db_conn, source)
    assert sorted(source.get_tickers()) == sorted(DEFAULT_TICKERS + ["PYPL"])
