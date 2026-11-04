"""FastAPI application: lifespan, background tasks, routers and static frontend."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, closing
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.chat import create_chat_router
from app.db import get_connection, get_tracked_tickers, init_db
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.portfolio.routes import create_portfolio_router
from app.portfolio.service import record_snapshot
from app.watchlist.routes import create_watchlist_router

BACKEND_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BACKEND_DIR / "static"
SNAPSHOT_INTERVAL = 30.0

load_dotenv(BACKEND_DIR.parent / ".env")  # local dev; Docker passes --env-file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

price_cache = PriceCache()
market_source = create_market_data_source(price_cache)


async def snapshot_loop(interval: float = SNAPSHOT_INTERVAL) -> None:
    """Record the portfolio's total value every ``interval`` seconds."""
    while True:
        await asyncio.sleep(interval)
        try:
            with closing(get_connection()) as conn:
                record_snapshot(conn, price_cache)
        except Exception:
            logger.exception("Portfolio snapshot failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Init the DB, start market data for tracked tickers, run the snapshot task."""
    init_db()
    with closing(get_connection()) as conn:
        await market_source.start(get_tracked_tickers(conn))
    task = asyncio.create_task(snapshot_loop())
    try:
        yield
    finally:
        task.cancel()
        await market_source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


app.include_router(create_stream_router(price_cache))
app.include_router(create_portfolio_router(price_cache, market_source))
app.include_router(create_watchlist_router(price_cache, market_source))
app.include_router(create_chat_router(price_cache, market_source))

if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
