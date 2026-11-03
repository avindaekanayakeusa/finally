"""Data models for market data."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_ticker(raw: str) -> str:
    """Return the canonical form of a ticker symbol ("  aapl " -> "AAPL").

    Raises ValueError for empty or malformed input. All market data entry
    points (sources, API routes) use this so "aapl" and "AAPL" are never
    tracked as two tickers.
    """
    ticker = (raw or "").strip().upper()
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return ticker


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """Immutable snapshot of one ticker's price at one point in time."""

    ticker: str
    price: float
    previous_price: float  # price at the previous update (tick-to-tick)
    timestamp: float = field(default_factory=time.time)  # Unix seconds
    session_open: float | None = None  # daily reference price (see day_change)

    # --- tick-to-tick (drives the flash animation) ---

    @property
    def change(self) -> float:
        """Absolute price change from the previous update."""
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
        """Percentage change from the previous update."""
        if self.previous_price == 0:
            return 0.0
        return round((self.price - self.previous_price) / self.previous_price * 100, 4)

    @property
    def direction(self) -> str:
        """'up', 'down', or 'flat' relative to previous_price."""
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    # --- daily (drives the watchlist "Chg %" column) ---

    @property
    def day_change(self) -> float | None:
        """Absolute change vs. session_open, or None if unknown."""
        if not self.session_open:
            return None
        return round(self.price - self.session_open, 4)

    @property
    def day_change_percent(self) -> float | None:
        """Percentage change vs. session_open, or None if unknown."""
        if not self.session_open:
            return None
        return round((self.price - self.session_open) / self.session_open * 100, 4)

    def to_dict(self) -> dict:
        """Serialize for JSON / SSE. Field names are the frontend contract."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent,
            "direction": self.direction,
            "session_open": self.session_open,
            "day_change": self.day_change,
            "day_change_percent": self.day_change_percent,
        }
