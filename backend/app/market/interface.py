"""Abstract interface for market data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataSource(ABC):
    """Contract for market data providers.

    Implementations push PriceUpdates into a shared PriceCache on their own
    schedule. Nothing downstream calls a source for prices; it reads the cache.

    Lifecycle:
        source = create_market_data_source(cache)
        await source.start(["AAPL", "GOOGL", ...])
        await source.add_ticker("PYPL")      # any time
        await source.remove_ticker("GOOGL")  # any time
        await source.stop()                  # on shutdown; idempotent

    Ticker arguments are normalized with normalize_ticker() by the
    implementation, so callers may pass "pypl" or " PYPL ".
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Start the background task. Call exactly once.

        Implementations SHOULD populate the cache before returning when they
        can (simulator: seed prices; Massive: one immediate poll), so the first
        SSE frame already has data.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Cancel the background task. Safe to call repeatedly. After it
        returns, the source never writes to the cache again."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Start tracking a ticker. No-op if already tracked."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and remove it from the cache. No-op if
        not tracked."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """Currently tracked tickers, in insertion order."""
