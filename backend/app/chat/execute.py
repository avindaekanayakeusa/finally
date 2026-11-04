"""Auto-execution of LLM-requested watchlist changes and trades."""

from __future__ import annotations

import sqlite3

from app.db import sync_tracked_tickers
from app.market import MarketDataSource, PriceCache
from app.portfolio.service import TradeError, execute_trade
from app.watchlist.service import WatchlistError, WatchlistNotFound, add_ticker, remove_ticker

from .schema import LLMResponse, TradeInstruction, WatchlistInstruction


async def execute_actions(
    conn: sqlite3.Connection, cache: PriceCache, source: MarketDataSource, response: LLMResponse
) -> dict:
    """Run watchlist changes first, then trades; return the §8 `actions` object."""
    changes = [
        await _apply_watchlist_change(conn, cache, source, c) for c in response.watchlist_changes
    ]
    trades = [_apply_trade(conn, cache, t) for t in response.trades]
    if trades:
        await sync_tracked_tickers(conn, source)
    return {"trades": trades, "watchlist_changes": changes}


async def _apply_watchlist_change(
    conn: sqlite3.Connection,
    cache: PriceCache,
    source: MarketDataSource,
    change: WatchlistInstruction,
) -> dict:
    """Apply one add/remove and report executed or failed with the error."""
    result = {"ticker": change.ticker.upper(), "action": change.action}
    try:
        if change.action == "add":
            await add_ticker(conn, cache, source, change.ticker)
        else:
            await remove_ticker(conn, source, change.ticker)
    except (WatchlistError, WatchlistNotFound) as e:
        return {**result, "status": "failed", "error": str(e)}
    return {**result, "status": "executed", "error": None}


def _apply_trade(conn: sqlite3.Connection, cache: PriceCache, trade: TradeInstruction) -> dict:
    """Execute one trade and report executed (with fill price) or failed."""
    result = {"ticker": trade.ticker.upper(), "side": trade.side, "quantity": trade.quantity}
    try:
        filled = execute_trade(conn, cache, trade.ticker, trade.side, trade.quantity)
    except TradeError as e:
        return {**result, "status": "failed", "price": None, "error": str(e)}
    return {**result, "status": "executed", "price": filled["price"], "error": None}
