"""Portfolio valuation, trade execution and value snapshots."""

from __future__ import annotations

import sqlite3

from app.db import DEFAULT_USER, new_id, now_iso, validate_ticker
from app.market import PriceCache

DUST = 1e-9
HISTORY_LIMIT = 1000


class TradeError(Exception):
    """A trade violated a business rule (maps to HTTP 400)."""


def get_cash(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> float:
    """Current cash balance for the user."""
    row = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)).fetchone()
    return row["cash_balance"]


def _position_dict(row: sqlite3.Row, cache: PriceCache) -> dict:
    """Value one position row at the cached price (falls back to avg_cost)."""
    price = cache.get_price(row["ticker"])
    current = price if price is not None else row["avg_cost"]
    cost_basis = row["quantity"] * row["avg_cost"]
    market_value = row["quantity"] * current
    pnl = market_value - cost_basis
    return {
        "ticker": row["ticker"],
        "quantity": row["quantity"],
        "avg_cost": row["avg_cost"],
        "current_price": current,
        "market_value": round(market_value, 2),
        "unrealized_pnl": round(pnl, 2),
        "pnl_percent": round(pnl / cost_basis * 100, 4) if cost_basis else 0.0,
    }


def get_portfolio(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> dict:
    """Cash, positions valued at live prices, and totals (PLAN §8 shape)."""
    rows = conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ? ORDER BY ticker",
        (user_id,),
    ).fetchall()
    positions = [_position_dict(r, cache) for r in rows]
    cash = get_cash(conn, user_id)
    positions_value = sum(p["market_value"] for p in positions)
    return {
        "cash_balance": round(cash, 2),
        "total_value": round(cash + positions_value, 2),
        "positions_value": round(positions_value, 2),
        "unrealized_pnl": round(sum(p["unrealized_pnl"] for p in positions), 2),
        "positions": positions,
    }


def execute_trade(
    conn: sqlite3.Connection,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = DEFAULT_USER,
) -> dict:
    """Fill a market order at the cached price; returns the trade dict.

    Writes the position, cash, trade row and a portfolio snapshot in one
    transaction. Raises TradeError on any business-rule failure.
    """
    try:
        ticker = validate_ticker(ticker)
    except ValueError as e:
        raise TradeError(str(e)) from None
    if side not in ("buy", "sell"):
        raise TradeError(f"Invalid side: {side!r} (must be 'buy' or 'sell')")
    if quantity <= 0:
        raise TradeError("Quantity must be greater than 0")
    price = cache.get_price(ticker)
    if price is None:
        raise TradeError(f"No price available for {ticker}. Add it to the watchlist first.")

    with conn:
        if side == "buy":
            _apply_buy(conn, user_id, ticker, quantity, price)
        else:
            _apply_sell(conn, user_id, ticker, quantity, price)
        trade = {
            "id": new_id(),
            "ticker": ticker,
            "side": side,
            "quantity": quantity,
            "price": price,
            "executed_at": now_iso(),
        }
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (:id, :user_id, :ticker, :side, :quantity, :price, :executed_at)",
            {**trade, "user_id": user_id},
        )
        _insert_snapshot(conn, cache, user_id)
    return trade


def _get_position(conn: sqlite3.Connection, user_id: str, ticker: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ).fetchone()


def _adjust_cash(conn: sqlite3.Connection, user_id: str, delta: float) -> None:
    conn.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?", (delta, user_id)
    )


def _apply_buy(conn, user_id: str, ticker: str, quantity: float, price: float) -> None:
    """Check cash, debit it, and add the lot at a weighted-average cost."""
    cost = quantity * price
    cash = get_cash(conn, user_id)
    if cash < cost:
        raise TradeError(f"Insufficient cash: need ${cost:.2f}, have ${cash:.2f}")
    _adjust_cash(conn, user_id, -cost)
    pos = _get_position(conn, user_id, ticker)
    if pos is None:
        conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_id(), user_id, ticker, quantity, price, now_iso()),
        )
        return
    new_qty = pos["quantity"] + quantity
    new_avg = (pos["quantity"] * pos["avg_cost"] + cost) / new_qty
    conn.execute(
        "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
        "WHERE user_id = ? AND ticker = ?",
        (new_qty, new_avg, now_iso(), user_id, ticker),
    )


def _apply_sell(conn, user_id: str, ticker: str, quantity: float, price: float) -> None:
    """Check holdings, credit cash, and reduce or delete the position."""
    pos = _get_position(conn, user_id, ticker)
    held = pos["quantity"] if pos else 0.0
    if held + DUST < quantity:
        raise TradeError(f"Insufficient shares: need {quantity:g} {ticker}, have {held:g}")
    _adjust_cash(conn, user_id, quantity * price)
    remaining = held - quantity
    if remaining < DUST:
        conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker))
    else:
        conn.execute(
            "UPDATE positions SET quantity = ?, updated_at = ? WHERE user_id = ? AND ticker = ?",
            (remaining, now_iso(), user_id, ticker),
        )


def _insert_snapshot(conn: sqlite3.Connection, cache: PriceCache, user_id: str) -> float:
    total = get_portfolio(conn, cache, user_id)["total_value"]
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (new_id(), user_id, total, now_iso()),
    )
    return total


def record_snapshot(conn: sqlite3.Connection, cache: PriceCache, user_id: str = DEFAULT_USER) -> float:
    """Persist the current total portfolio value; returns it."""
    with conn:
        return _insert_snapshot(conn, cache, user_id)


def get_history(conn: sqlite3.Connection, user_id: str = DEFAULT_USER) -> list[dict]:
    """Latest HISTORY_LIMIT snapshots, oldest first."""
    rows = conn.execute(
        "SELECT total_value, recorded_at FROM ("
        "  SELECT total_value, recorded_at FROM portfolio_snapshots WHERE user_id = ?"
        "  ORDER BY recorded_at DESC LIMIT ?"
        ") ORDER BY recorded_at",
        (user_id, HISTORY_LIMIT),
    ).fetchall()
    return [dict(r) for r in rows]
