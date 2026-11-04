"""Portfolio context given to the LLM on every chat turn."""

from __future__ import annotations

import json
import sqlite3

from app.market import PriceCache
from app.portfolio.service import get_portfolio
from app.watchlist.service import list_watchlist


def build_context(conn: sqlite3.Connection, cache: PriceCache) -> str:
    """Current cash, positions with P&L, totals and watchlist prices, as JSON text."""
    portfolio = get_portfolio(conn, cache)
    watchlist = [
        {"ticker": w["ticker"], "price": w["price"]} for w in list_watchlist(conn, cache)
    ]
    data = {"portfolio": portfolio, "watchlist": watchlist}
    return "Current portfolio and watchlist (live prices):\n" + json.dumps(data)
