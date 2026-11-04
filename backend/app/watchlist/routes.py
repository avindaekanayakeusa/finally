"""Watchlist REST endpoints."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.db import get_db
from app.market import MarketDataSource, PriceCache

from .service import WatchlistError, WatchlistNotFound, add_ticker, list_watchlist, remove_ticker


class WatchlistAdd(BaseModel):
    """Body of POST /api/watchlist."""

    ticker: str


def create_watchlist_router(cache: PriceCache, source: MarketDataSource) -> APIRouter:
    """Build the /api/watchlist router bound to the shared cache and source."""
    router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

    @router.get("")
    def read_watchlist(conn: sqlite3.Connection = Depends(get_db)) -> dict:
        """Watchlist tickers with latest prices."""
        return {"tickers": list_watchlist(conn, cache)}

    @router.post("", status_code=201)
    async def add(body: WatchlistAdd, conn: sqlite3.Connection = Depends(get_db)) -> dict:
        """Add a ticker and start streaming it."""
        try:
            return await add_ticker(conn, cache, source, body.ticker)
        except WatchlistError as e:
            raise HTTPException(400, str(e)) from None

    @router.delete("/{ticker}", status_code=204)
    async def remove(ticker: str, conn: sqlite3.Connection = Depends(get_db)) -> Response:
        """Remove a ticker (keeps streaming it if a position is held)."""
        try:
            await remove_ticker(conn, source, ticker)
        except WatchlistError as e:
            raise HTTPException(400, str(e)) from None
        except WatchlistNotFound as e:
            raise HTTPException(404, str(e)) from None
        return Response(status_code=204)

    return router
