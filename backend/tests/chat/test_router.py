"""POST /api/chat end to end against a temp database."""

import json

from app.chat import router as chat_router
from app.chat.schema import LLMResponse, TradeInstruction, WatchlistInstruction
from tests.chat.conftest import PRICE


def stored_messages(db_conn):
    rows = db_conn.execute(
        "SELECT role, content, actions FROM chat_messages ORDER BY created_at"
    ).fetchall()
    return [dict(r) for r in rows]


def fake_llm(monkeypatch, response=None, error=None, seen=None):
    """Replace the LLM call with a fixed response or error; record messages in `seen`."""

    async def _fake(messages, user_message):
        if seen is not None:
            seen.append(messages)
        if error:
            raise error
        return response

    monkeypatch.setattr(chat_router, "get_llm_response", _fake)


def test_mock_buy_executes_and_stores(mock_mode, client, db_conn):
    r = client.post("/api/chat", json={"message": "buy"})
    assert r.status_code == 200
    body = r.json()
    assert body["message"] == "Mock: buying 1 AAPL."
    assert body["actions"] == {
        "trades": [
            {"ticker": "AAPL", "side": "buy", "quantity": 1, "status": "executed", "price": PRICE, "error": None}
        ],
        "watchlist_changes": [],
    }
    pos = db_conn.execute("SELECT quantity FROM positions WHERE ticker = 'AAPL'").fetchone()
    assert pos["quantity"] == 1
    msgs = stored_messages(db_conn)
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "buy"),
        ("assistant", "Mock: buying 1 AAPL."),
    ]
    assert msgs[0]["actions"] is None
    assert json.loads(msgs[1]["actions"]) == body["actions"]


def test_mock_sell_without_shares_reports_failure(mock_mode, client):
    trade = client.post("/api/chat", json={"message": "sell"}).json()["actions"]["trades"][0]
    assert trade["status"] == "failed"
    assert trade["price"] is None
    assert "Insufficient shares" in trade["error"]


def test_mock_watch_adds_pypl(mock_mode, client, db_conn, source):
    change = client.post("/api/chat", json={"message": "watch"}).json()["actions"]["watchlist_changes"]
    assert change == [{"ticker": "PYPL", "action": "add", "status": "executed", "error": None}]
    assert "PYPL" in source.get_tickers()
    second = client.post("/api/chat", json={"message": "watch"}).json()
    assert second["actions"]["watchlist_changes"][0]["status"] == "failed"
    assert "already on the watchlist" in second["actions"]["watchlist_changes"][0]["error"]


def test_watchlist_changes_run_before_trades(monkeypatch, client):
    fake_llm(
        monkeypatch,
        LLMResponse(
            message="Adding and buying PYPL.",
            trades=[TradeInstruction(ticker="PYPL", side="buy", quantity=5)],
            watchlist_changes=[WatchlistInstruction(ticker="PYPL", action="add")],
        ),
    )
    actions = client.post("/api/chat", json={"message": "add pypl and buy 5"}).json()["actions"]
    assert actions["watchlist_changes"][0]["status"] == "executed"
    assert actions["trades"][0]["status"] == "executed"


def test_insufficient_cash_reported(monkeypatch, client):
    fake_llm(
        monkeypatch,
        LLMResponse(
            message="Buying a lot.",
            trades=[TradeInstruction(ticker="AAPL", side="buy", quantity=1000)],
            watchlist_changes=[],
        ),
    )
    trade = client.post("/api/chat", json={"message": "buy 1000"}).json()["actions"]["trades"][0]
    assert trade["status"] == "failed"
    assert "Insufficient cash" in trade["error"]


def test_llm_failure_returns_502_and_stores_nothing(monkeypatch, client, db_conn):
    fake_llm(monkeypatch, error=RuntimeError("boom"))
    r = client.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 502
    assert "boom" in r.json()["detail"]
    assert stored_messages(db_conn) == []


def test_prompt_has_context_and_history(mock_mode, monkeypatch, client):
    client.post("/api/chat", json={"message": "first"})
    seen = []
    fake_llm(monkeypatch, LLMResponse(message="ok", trades=[], watchlist_changes=[]), seen=seen)
    client.post("/api/chat", json={"message": "second"})
    messages = seen[0]
    assert messages[0]["role"] == "system" and "FinAlly" in messages[0]["content"]
    assert '"cash_balance": 10000.0' in messages[1]["content"]
    assert [m["content"] for m in messages[2:]] == [
        "first",
        "Mock: I am FinAlly, your AI trading assistant.",
        "second",
    ]


def test_history_limited_to_last_20(mock_mode, monkeypatch, client):
    for i in range(12):
        client.post("/api/chat", json={"message": f"msg {i}"})
    seen = []
    fake_llm(monkeypatch, LLMResponse(message="ok", trades=[], watchlist_changes=[]), seen=seen)
    client.post("/api/chat", json={"message": "last"})
    history = seen[0][2:-1]
    assert len(history) == 20
    assert history[0]["content"] == "msg 2"
