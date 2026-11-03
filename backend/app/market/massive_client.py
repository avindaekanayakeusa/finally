"""Massive (formerly Polygon.io) REST client for real market data."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from massive import RESTClient
from massive.exceptions import AuthError, BadResponse
from massive.rest.models import SnapshotMarketType

from .cache import PriceCache
from .interface import MarketDataSource
from .models import normalize_ticker

logger = logging.getLogger(__name__)

NS_PER_SECOND = 1_000_000_000


def parse_snapshot(snap: Any) -> tuple[str, float, float, float | None] | None:
    """Extract (ticker, price, timestamp_seconds, session_open) from a TickerSnapshot.

    Pure function, no I/O. Price falls back last_trade -> min -> day -> prev_day.
    Timestamps in the SDK are nanoseconds (``last_trade.sip_timestamp``, then
    ``updated``). ``session_open`` is ``prev_day.close`` (daily-change reference).
    Returns None when the snapshot has no usable price.
    """
    ticker = getattr(snap, "ticker", None)
    if not ticker:
        return None

    last_trade = getattr(snap, "last_trade", None)
    minute = getattr(snap, "min", None)
    day = getattr(snap, "day", None)
    prev_day = getattr(snap, "prev_day", None)

    price = None
    for candidate in (
        getattr(last_trade, "price", None),
        getattr(minute, "close", None),
        getattr(day, "close", None),
        getattr(prev_day, "close", None),
    ):
        if candidate:  # skips None and 0
            price = float(candidate)
            break
    if price is None:
        return None

    ts_ns = getattr(last_trade, "sip_timestamp", None) or getattr(snap, "updated", None)
    timestamp = ts_ns / NS_PER_SECOND if ts_ns else time.time()

    prev_close = getattr(prev_day, "close", None)
    session_open = float(prev_close) if prev_close else None

    return ticker.upper(), price, timestamp, session_open


class MassiveDataSource(MarketDataSource):
    """Polls the Massive snapshot endpoint for all tracked tickers in one call.

    Rate limits: free tier 5 req/min -> 15 s default; paid tiers -> 2-5 s.
    On failures the interval backs off exponentially (capped at MAX_BACKOFF)
    and resets on the next success.
    """

    MAX_BACKOFF = 120.0

    def __init__(
        self,
        api_key: str,
        price_cache: PriceCache,
        poll_interval: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._cache = price_cache
        self._interval = poll_interval
        self._tickers: list[str] = []
        self._task: asyncio.Task | None = None
        self._client: RESTClient | None = None
        self._consecutive_failures = 0

    async def start(self, tickers: list[str]) -> None:
        self._client = RESTClient(api_key=self._api_key)
        self._tickers = list(dict.fromkeys(normalize_ticker(t) for t in tickers))
        await self._poll_once()  # data before the first SSE frame
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info(
            "Massive poller started: %d tickers, %.1fs interval",
            len(self._tickers),
            self._interval,
        )

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._client = None
        logger.info("Massive poller stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if ticker in self._tickers:
            return
        self._tickers.append(ticker)
        logger.info("Massive: added %s", ticker)
        # Price it now rather than up to one interval later, so it is tradable at once.
        # One extra call per add; on the free tier this shares the 5/min budget.
        await self._poll_once(only=[ticker])

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        self._tickers = [t for t in self._tickers if t != ticker]
        self._cache.remove(ticker)
        logger.info("Massive: removed %s", ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ---- internals ----

    def _next_delay(self) -> float:
        if self._consecutive_failures == 0:
            return self._interval
        return min(self._interval * 2**self._consecutive_failures, self.MAX_BACKOFF)

    async def _poll_loop(self) -> None:
        """Poll on interval. The first poll already happened in start()."""
        while True:
            await asyncio.sleep(self._next_delay())
            await self._poll_once()

    async def _poll_once(self, only: list[str] | None = None) -> None:
        """One poll cycle: fetch snapshots in a worker thread, update the cache."""
        tickers = list(only or self._tickers)  # copy: the list may change mid-call
        if not tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(self._fetch_snapshots, tickers)
        except AuthError as e:
            self._consecutive_failures += 1
            logger.error("Massive auth failed (check MASSIVE_API_KEY): %s", e)
            return
        except BadResponse as e:  # 403 plan limits, 429 rate limit, 5xx
            self._consecutive_failures += 1
            logger.warning("Massive bad response: %s", e)
            return
        except Exception as e:  # network, timeouts, JSON
            self._consecutive_failures += 1
            logger.warning("Massive poll failed: %s", e)
            return

        self._consecutive_failures = 0
        tracked = set(self._tickers)  # ignore tickers removed while the call was in flight
        updated = 0
        seen: set[str] = set()
        for snap in snapshots:
            parsed = parse_snapshot(snap)
            if parsed is None:
                logger.debug("Massive: unusable snapshot for %s", getattr(snap, "ticker", "?"))
                continue
            ticker, price, ts, session_open = parsed
            seen.add(ticker)
            if ticker not in tracked:
                continue
            self._cache.update(ticker, price, timestamp=ts, session_open=session_open)
            updated += 1

        missing = set(tickers) - seen
        if missing:
            logger.info(
                "Massive: no data for %s (unknown symbol or no trades yet)",
                ", ".join(sorted(missing)),
            )
        logger.debug("Massive poll: %d/%d updated", updated, len(tickers))

    def _fetch_snapshots(self, tickers: list[str]) -> list:
        """Blocking SDK call - always run via asyncio.to_thread."""
        assert self._client is not None
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=tickers,
        )
