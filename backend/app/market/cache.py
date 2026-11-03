"""Thread-safe in-memory price cache."""

from __future__ import annotations

import time
from threading import Lock

from .models import PriceUpdate


class PriceCache:
    """Latest PriceUpdate per ticker, plus a monotonic version counter.

    Writers: the active MarketDataSource (simulator task, or Massive poll
             results delivered from a worker thread).
    Readers: SSE stream, portfolio valuation, trade execution, LLM context.
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = Lock()
        self._version = 0  # bumped on every write and every effective remove

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: float | None = None,
        session_open: float | None = None,
    ) -> PriceUpdate:
        """Record a new price and return the resulting PriceUpdate.

        - First update for a ticker: previous_price == price (direction 'flat').
        - session_open: if omitted, the previous value is carried forward, so
          sources only need to supply it when it changes.
        """
        with self._lock:
            ts = time.time() if timestamp is None else timestamp
            prev = self._prices.get(ticker)
            previous_price = prev.price if prev else price
            if session_open is None and prev is not None:
                session_open = prev.session_open

            update = PriceUpdate(
                ticker=ticker,
                price=round(price, 2),
                previous_price=round(previous_price, 2),
                timestamp=ts,
                session_open=round(session_open, 2) if session_open else None,
            )
            self._prices[ticker] = update
            self._version += 1
            return update

    def get(self, ticker: str) -> PriceUpdate | None:
        """Latest update for a ticker, or None if unknown."""
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        """Convenience: just the price float, or None."""
        update = self.get(ticker)
        return update.price if update else None

    def get_all(self) -> dict[str, PriceUpdate]:
        """Shallow copy of all prices (values are immutable, so this is safe)."""
        with self._lock:
            return dict(self._prices)

    def snapshot(self) -> tuple[int, dict[str, PriceUpdate]]:
        """Atomically read (version, prices). Used by the SSE loop."""
        with self._lock:
            return self._version, dict(self._prices)

    def remove(self, ticker: str) -> None:
        """Remove a ticker. Bumps the version so SSE pushes a frame without it."""
        with self._lock:
            if self._prices.pop(ticker, None) is not None:
                self._version += 1

    @property
    def version(self) -> int:
        """Current version counter, for change detection."""
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
