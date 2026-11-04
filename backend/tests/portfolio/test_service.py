"""Tests for portfolio valuation and trade execution."""

import pytest

from app.market import PriceCache
from app.portfolio.service import (
    TradeError,
    execute_trade,
    get_history,
    get_portfolio,
    record_snapshot,
)


@pytest.fixture
def cache():
    c = PriceCache()
    c.update("AAPL", 100.0)
    c.update("MSFT", 400.0)
    return c


def _count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_empty_portfolio(db_conn, cache):
    p = get_portfolio(db_conn, cache)
    assert p == {"cash_balance": 10000.0, "total_value": 10000.0, "positions_value": 0,
                 "unrealized_pnl": 0, "positions": []}


def test_buy_creates_position_and_debits_cash(db_conn, cache):
    trade = execute_trade(db_conn, cache, "aapl", "buy", 10)
    assert trade["ticker"] == "AAPL" and trade["price"] == 100.0 and trade["side"] == "buy"
    assert trade["executed_at"].endswith("Z")
    p = get_portfolio(db_conn, cache)
    assert p["cash_balance"] == 9000.0
    assert p["positions"][0]["quantity"] == 10
    assert p["total_value"] == 10000.0
    assert _count(db_conn, "trades") == 1
    assert _count(db_conn, "portfolio_snapshots") == 1


def test_buy_weighted_average_cost(db_conn, cache):
    execute_trade(db_conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 200.0)
    execute_trade(db_conn, cache, "AAPL", "buy", 10)
    pos = get_portfolio(db_conn, cache)["positions"][0]
    assert pos["quantity"] == 20
    assert pos["avg_cost"] == pytest.approx(150.0)
    assert pos["unrealized_pnl"] == pytest.approx(1000.0)
    assert pos["pnl_percent"] == pytest.approx(33.3333, abs=1e-3)


def test_sell_at_loss_keeps_avg_cost(db_conn, cache):
    execute_trade(db_conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 80.0)
    execute_trade(db_conn, cache, "AAPL", "sell", 4)
    p = get_portfolio(db_conn, cache)
    pos = p["positions"][0]
    assert pos["quantity"] == 6 and pos["avg_cost"] == 100.0
    assert pos["unrealized_pnl"] == pytest.approx(-120.0)
    assert p["cash_balance"] == pytest.approx(9000 + 320)


def test_sell_all_deletes_position(db_conn, cache):
    execute_trade(db_conn, cache, "AAPL", "buy", 0.3)
    execute_trade(db_conn, cache, "AAPL", "sell", 0.1)
    execute_trade(db_conn, cache, "AAPL", "sell", 0.2)
    assert get_portfolio(db_conn, cache)["positions"] == []
    assert get_portfolio(db_conn, cache)["cash_balance"] == pytest.approx(10000.0)


def test_insufficient_cash(db_conn, cache):
    with pytest.raises(TradeError, match=r"Insufficient cash: need \$40400.00, have \$10000.00"):
        execute_trade(db_conn, cache, "MSFT", "buy", 101)
    assert _count(db_conn, "trades") == 0


def test_sell_more_than_owned(db_conn, cache):
    execute_trade(db_conn, cache, "AAPL", "buy", 1)
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade(db_conn, cache, "AAPL", "sell", 2)
    with pytest.raises(TradeError, match="Insufficient shares"):
        execute_trade(db_conn, cache, "MSFT", "sell", 1)


@pytest.mark.parametrize("ticker,side,qty,msg", [
    ("AAPL", "buy", 0, "greater than 0"),
    ("AAPL", "buy", -1, "greater than 0"),
    ("BAD1", "buy", 1, "Invalid ticker"),
    ("AAPL", "hold", 1, "Invalid side"),
    ("NFLX", "buy", 1, "No price available"),
])
def test_validation_errors(db_conn, cache, ticker, side, qty, msg):
    with pytest.raises(TradeError, match=msg):
        execute_trade(db_conn, cache, ticker, side, qty)


def test_position_without_price_falls_back_to_avg_cost(db_conn, cache):
    execute_trade(db_conn, cache, "AAPL", "buy", 10)
    cache.remove("AAPL")
    pos = get_portfolio(db_conn, cache)["positions"][0]
    assert pos["current_price"] == 100.0 and pos["unrealized_pnl"] == 0


def test_history_oldest_first(db_conn, cache):
    record_snapshot(db_conn, cache)
    execute_trade(db_conn, cache, "AAPL", "buy", 10)
    cache.update("AAPL", 110.0)
    record_snapshot(db_conn, cache)
    values = [s["total_value"] for s in get_history(db_conn)]
    assert values == [10000.0, 10000.0, 10100.0]
