"""Ticker validation and tracked-ticker reconciliation with the market source."""

from __future__ import annotations

import re
import sqlite3

from app.market import MarketDataSource

from .connection import DEFAULT_USER

_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")


def validate_ticker(raw: str) -> str:
    """Uppercase and validate a ticker (1-5 letters). Raises ValueError if invalid."""
    ticker = (raw or "").strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Invalid ticker: {raw!r} (must be 1-5 letters)")
    return ticker


def get_tracked_tickers(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[str]:
    """Union of watchlist tickers and tickers with an open position, watchlist order first."""
    rows = conn.execute(
        """
        SELECT ticker FROM (
            SELECT ticker, added_at AS t, 0 AS grp FROM watchlist WHERE user_id = ?
            UNION
            SELECT ticker, updated_at AS t, 1 AS grp FROM positions WHERE user_id = ?
        ) ORDER BY grp, t
        """,
        (user_id, user_id),
    ).fetchall()
    return list(dict.fromkeys(r["ticker"] for r in rows))


async def sync_tracked_tickers(conn: sqlite3.Connection, source: MarketDataSource) -> None:
    """Reconcile the source's ticker set with watchlist ∪ positions. Idempotent."""
    wanted = get_tracked_tickers(conn)
    current = set(source.get_tickers())
    for ticker in wanted:
        if ticker not in current:
            await source.add_ticker(ticker)
    for ticker in current - set(wanted):
        await source.remove_ticker(ticker)
