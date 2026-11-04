"""Watchlist CRUD, kept in sync with the market data source."""

from __future__ import annotations

import sqlite3

from app.db import DEFAULT_USER, new_id, now_iso, sync_tracked_tickers, validate_ticker
from app.market import MarketDataSource, PriceCache


class WatchlistError(Exception):
    """Invalid ticker or duplicate add (maps to HTTP 400)."""


class WatchlistNotFound(Exception):  # noqa: N818  (name fixed by planning/TEAM.md)
    """Ticker is not on the watchlist (maps to HTTP 404)."""


def _entry(ticker: str, added_at: str, cache: PriceCache) -> dict:
    """Watchlist item with the latest cached price, or nulls if none yet."""
    update = cache.get(ticker)
    return {
        "ticker": ticker,
        "price": update.price if update else None,
        "previous_price": update.previous_price if update else None,
        "direction": update.direction if update else None,
        "added_at": added_at,
    }


def list_watchlist(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> list[dict]:
    """Watchlist entries ordered by added_at, with latest prices."""
    rows = conn.execute(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (user_id,),
    ).fetchall()
    return [_entry(r["ticker"], r["added_at"], cache) for r in rows]


def _parse(raw: str) -> str:
    try:
        return validate_ticker(raw)
    except ValueError as e:
        raise WatchlistError(str(e)) from None


async def add_ticker(
    conn: sqlite3.Connection,
    cache: PriceCache,
    source: MarketDataSource,
    ticker: str,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Add a ticker, start tracking it, and return the new entry."""
    ticker = _parse(ticker)
    added_at = now_iso()
    try:
        with conn:
            conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (new_id(), user_id, ticker, added_at),
            )
    except sqlite3.IntegrityError:
        raise WatchlistError(f"{ticker} is already on the watchlist") from None
    await sync_tracked_tickers(conn, source)
    return _entry(ticker, added_at, cache)


async def remove_ticker(
    conn: sqlite3.Connection,
    source: MarketDataSource,
    ticker: str,
    user_id: str = DEFAULT_USER,
) -> None:
    """Remove a ticker; tracking continues if a position is still held."""
    ticker = _parse(ticker)
    with conn:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
        )
    if cur.rowcount == 0:
        raise WatchlistNotFound(f"{ticker} is not on the watchlist")
    await sync_tracked_tickers(conn, source)
