"""Tests for watchlist CRUD and source syncing."""

import pytest

from app.db import DEFAULT_TICKERS
from app.market import PriceCache
from app.market.simulator import SimulatorDataSource
from app.portfolio.service import execute_trade
from app.watchlist.service import (
    WatchlistError,
    WatchlistNotFound,
    add_ticker,
    list_watchlist,
    remove_ticker,
)


@pytest.fixture
async def market():
    cache = PriceCache()
    source = SimulatorDataSource(price_cache=cache, update_interval=60)
    await source.start(list(DEFAULT_TICKERS))
    yield cache, source
    await source.stop()


async def test_list_default_watchlist_with_prices(db_conn, market):
    cache, _ = market
    items = list_watchlist(db_conn, cache)
    assert [i["ticker"] for i in items] == DEFAULT_TICKERS
    assert items[0]["price"] > 0 and items[0]["direction"] in ("up", "down", "flat")


def test_list_without_prices_is_null(db_conn):
    item = list_watchlist(db_conn, PriceCache())[0]
    assert item["price"] is None and item["previous_price"] is None and item["direction"] is None


async def test_add_ticker_tracks_and_prices(db_conn, market):
    cache, source = market
    entry = await add_ticker(db_conn, cache, source, "pypl")
    assert entry["ticker"] == "PYPL" and entry["price"] > 0
    assert "PYPL" in source.get_tickers()
    assert list_watchlist(db_conn, cache)[-1]["ticker"] == "PYPL"


async def test_add_duplicate_and_invalid(db_conn, market):
    cache, source = market
    with pytest.raises(WatchlistError, match="already on the watchlist"):
        await add_ticker(db_conn, cache, source, "AAPL")
    with pytest.raises(WatchlistError, match="Invalid ticker"):
        await add_ticker(db_conn, cache, source, "BRK.B")


async def test_remove_ticker_stops_tracking(db_conn, market):
    cache, source = market
    await remove_ticker(db_conn, source, "nflx")
    assert "NFLX" not in source.get_tickers()
    assert "NFLX" not in cache
    assert "NFLX" not in [i["ticker"] for i in list_watchlist(db_conn, cache)]


async def test_remove_held_ticker_keeps_tracking(db_conn, market):
    cache, source = market
    execute_trade(db_conn, cache, "NFLX", "buy", 1)
    await remove_ticker(db_conn, source, "NFLX")
    assert "NFLX" in source.get_tickers()
    execute_trade(db_conn, cache, "NFLX", "sell", 1)
    from app.db import sync_tracked_tickers
    await sync_tracked_tickers(db_conn, source)
    assert "NFLX" not in source.get_tickers()


async def test_remove_missing_ticker(db_conn, market):
    _, source = market
    with pytest.raises(WatchlistNotFound):
        await remove_ticker(db_conn, source, "PYPL")
