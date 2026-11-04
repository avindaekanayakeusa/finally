"""Mock LLM rules (PLAN §9 table)."""

from app.chat.mock import mock_response


def test_buy():
    r = mock_response("Please BUY something")
    assert r.message == "Mock: buying 1 AAPL."
    assert [t.model_dump() for t in r.trades] == [{"ticker": "AAPL", "side": "buy", "quantity": 1}]
    assert r.watchlist_changes == []


def test_sell():
    r = mock_response("sell it")
    assert r.message == "Mock: selling 1 AAPL."
    assert [t.model_dump() for t in r.trades] == [{"ticker": "AAPL", "side": "sell", "quantity": 1}]


def test_watch():
    r = mock_response("Watch PYPL")
    assert r.message == "Mock: adding PYPL to your watchlist."
    assert r.trades == []
    assert [c.model_dump() for c in r.watchlist_changes] == [{"ticker": "PYPL", "action": "add"}]


def test_first_match_wins():
    assert mock_response("sell then buy").message == "Mock: buying 1 AAPL."


def test_default():
    r = mock_response("hello")
    assert r.message == "Mock: I am FinAlly, your AI trading assistant."
    assert r.trades == [] and r.watchlist_changes == []
