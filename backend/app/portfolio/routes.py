"""Portfolio REST endpoints."""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_db, sync_tracked_tickers
from app.market import MarketDataSource, PriceCache

from .service import TradeError, execute_trade, get_history, get_portfolio


class TradeRequest(BaseModel):
    """Body of POST /api/portfolio/trade."""

    ticker: str
    quantity: float
    side: Literal["buy", "sell"]


def create_portfolio_router(cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/portfolio router bound to the shared cache and source."""
    router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

    @router.get("")
    def read_portfolio(conn: sqlite3.Connection = Depends(get_db)) -> dict:
        """Cash, positions and totals at live prices."""
        return get_portfolio(conn, cache)

    @router.post("/trade")
    async def trade(body: TradeRequest, conn: sqlite3.Connection = Depends(get_db)) -> dict:
        """Execute a market order and return the trade plus updated portfolio."""
        try:
            result = execute_trade(conn, cache, body.ticker, body.side, body.quantity)
        except TradeError as e:
            raise HTTPException(400, str(e)) from None
        await sync_tracked_tickers(conn, source)
        return {"trade": result, "portfolio": get_portfolio(conn, cache)}

    @router.get("/history")
    def history(conn: sqlite3.Connection = Depends(get_db)) -> dict:
        """Portfolio value snapshots, oldest first."""
        return {"snapshots": get_history(conn)}

    return router
