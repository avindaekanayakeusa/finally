"""End-to-end tests of the FastAPI app (real lifespan, simulator, temp DB)."""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "api.db"))
    for ticker in list(main.price_cache.get_all()):
        main.price_cache.remove(ticker)
    with TestClient(main.app) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_watchlist_default(client):
    tickers = client.get("/api/watchlist").json()["tickers"]
    assert len(tickers) == 10 and tickers[0]["ticker"] == "AAPL"
    assert tickers[0]["price"] > 0 and tickers[0]["added_at"].endswith("Z")


def test_watchlist_add_remove(client):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 201 and r.json()["ticker"] == "PYPL" and r.json()["price"] > 0
    assert client.post("/api/watchlist", json={"ticker": "PYPL"}).status_code == 400
    assert client.post("/api/watchlist", json={"ticker": "BAD123"}).status_code == 400
    assert client.post("/api/watchlist", json={}).status_code == 422
    r = client.delete("/api/watchlist/PYPL")
    assert r.status_code == 204 and r.content == b""
    assert client.delete("/api/watchlist/PYPL").status_code == 404
    assert "PYPL" not in main.market_source.get_tickers()


def test_portfolio_initial(client):
    p = client.get("/api/portfolio").json()
    assert p["cash_balance"] == 10000.0 and p["total_value"] == 10000.0 and p["positions"] == []


def test_buy_and_sell(client):
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["trade"]["ticker"] == "AAPL" and body["trade"]["side"] == "buy"
    assert body["portfolio"]["positions"][0]["quantity"] == 2
    assert body["portfolio"]["cash_balance"] < 10000.0
    r = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 2, "side": "sell"})
    assert r.status_code == 200 and r.json()["portfolio"]["positions"] == []
    assert len(client.get("/api/portfolio/history").json()["snapshots"]) == 2


@pytest.mark.parametrize("body,status", [
    ({"ticker": "AAPL", "quantity": 1000, "side": "buy"}, 400),
    ({"ticker": "AAPL", "quantity": 1, "side": "sell"}, 400),
    ({"ticker": "AAPL", "quantity": 0, "side": "buy"}, 400),
    ({"ticker": "PYPL", "quantity": 1, "side": "buy"}, 400),
    ({"ticker": "AAPL", "quantity": 1, "side": "short"}, 422),
    ({"ticker": "AAPL", "side": "buy"}, 422),
])
def test_trade_errors(client, body, status):
    r = client.post("/api/portfolio/trade", json=body)
    assert r.status_code == status
    assert "detail" in r.json()


def test_held_ticker_streams_after_watchlist_remove(client):
    client.post("/api/portfolio/trade", json={"ticker": "NFLX", "quantity": 1, "side": "buy"})
    client.delete("/api/watchlist/NFLX")
    assert "NFLX" in main.market_source.get_tickers()
    pos = client.get("/api/portfolio").json()["positions"][0]
    assert pos["ticker"] == "NFLX"
    client.post("/api/portfolio/trade", json={"ticker": "NFLX", "quantity": 1, "side": "sell"})
    assert "NFLX" not in main.market_source.get_tickers()


def test_history_empty(client):
    assert client.get("/api/portfolio/history").json() == {"snapshots": []}


async def test_snapshot_loop_records(db_conn):
    import asyncio

    task = asyncio.create_task(main.snapshot_loop(interval=0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    assert db_conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] >= 2
