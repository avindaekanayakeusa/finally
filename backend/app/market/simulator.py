"""GBM-based market simulator."""

from __future__ import annotations

import asyncio
import logging
import math

import numpy as np

from .cache import PriceCache
from .interface import MarketDataSource
from .models import normalize_ticker
from .seed_prices import (
    CORRELATION_GROUPS,
    CROSS_GROUP_CORR,
    DEFAULT_PARAMS,
    INTRA_FINANCE_CORR,
    INTRA_TECH_CORR,
    SEED_PRICES,
    TICKER_PARAMS,
    TSLA_CORR,
    UNKNOWN_SEED_RANGE,
)

logger = logging.getLogger(__name__)


class GBMSimulator:
    """Correlated Geometric Brownian Motion for a dynamic set of tickers.

    Math (exact discretization):
        S(t+dt) = S(t) * exp((mu - sigma^2/2) * dt + sigma * sqrt(dt) * Z)

    where Z are correlated standard normals, Z = L @ eps, L = cholesky(C).
    The tiny dt (~8.5e-8 for 500ms ticks over a 252-day, 6.5h trading year)
    produces cent-level moves per tick that accumulate naturally.

    Pure and synchronous (no asyncio, no cache), so it is easy to unit test.
    Pass a seeded ``rng`` for deterministic output.
    """

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR  # ~8.48e-8

    def __init__(
        self,
        tickers: list[str],
        dt: float = DEFAULT_DT,
        event_probability: float = 0.001,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._dt = dt
        self._sqrt_dt = math.sqrt(dt)
        self._event_prob = event_probability
        self._rng = rng or np.random.default_rng()

        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._opens: dict[str, float] = {}  # session_open per ticker
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for ticker in tickers:
            self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    # ---- public API -------------------------------------------------------

    def step(self) -> dict[str, float]:
        """Advance every ticker one tick. Returns {ticker: new_price}."""
        n = len(self._tickers)
        if n == 0:
            return {}

        eps = self._rng.standard_normal(n)
        z = self._cholesky @ eps if self._cholesky is not None else eps

        result: dict[str, float] = {}
        for i, ticker in enumerate(self._tickers):
            mu = self._params[ticker]["mu"]
            sigma = self._params[ticker]["sigma"]

            drift = (mu - 0.5 * sigma * sigma) * self._dt
            diffusion = sigma * self._sqrt_dt * z[i]
            price = self._prices[ticker] * math.exp(drift + diffusion)

            # Occasional 2-5% shock: ~one event every 50s across 10 tickers at 2 ticks/s
            if self._rng.random() < self._event_prob:
                shock = self._rng.uniform(0.02, 0.05) * (1 if self._rng.random() < 0.5 else -1)
                price *= 1 + shock
                logger.debug("Shock on %s: %+.1f%%", ticker, shock * 100)

            self._prices[ticker] = price  # keep full precision internally
            result[ticker] = round(price, 2)  # round only on the way out
        return result

    def add_ticker(self, ticker: str) -> None:
        """Add a ticker. Rebuilds the correlation matrix. No-op if present."""
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker. Rebuilds the correlation matrix. No-op if absent."""
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker], self._opens[ticker], self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        """Current (full-precision) price, or None if not tracked."""
        return self._prices.get(ticker)

    def get_session_open(self, ticker: str) -> float | None:
        """Price when the ticker started being simulated, or None."""
        return self._opens.get(ticker)

    def get_tickers(self) -> list[str]:
        """Tracked tickers in insertion order."""
        return list(self._tickers)

    # ---- internals --------------------------------------------------------

    def _add_ticker_internal(self, ticker: str) -> None:
        """Add without rebuilding Cholesky (for batch initialization)."""
        if ticker in self._prices:
            return
        seed = SEED_PRICES.get(ticker)
        if seed is None:
            seed = float(self._rng.uniform(*UNKNOWN_SEED_RANGE))
        self._tickers.append(ticker)
        self._prices[ticker] = seed
        self._opens[ticker] = seed
        self._params[ticker] = dict(TICKER_PARAMS.get(ticker, DEFAULT_PARAMS))

    def _rebuild_cholesky(self) -> None:
        """O(n^2) rebuild on add/remove; n is small (< 50)."""
        n = len(self._tickers)
        if n <= 1:
            self._cholesky = None
            return
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho = self._pairwise_correlation(self._tickers[i], self._tickers[j])
                corr[i, j] = corr[j, i] = rho
        try:
            self._cholesky = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            logger.error("Correlation matrix not positive-definite; using independent moves")
            self._cholesky = None

    @staticmethod
    def _pairwise_correlation(t1: str, t2: str) -> float:
        """Sector-based correlation: tech 0.6, finance 0.5, TSLA/cross 0.3."""
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        tech, fin = CORRELATION_GROUPS["tech"], CORRELATION_GROUPS["finance"]
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in fin and t2 in fin:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR


class SimulatorDataSource(MarketDataSource):
    """Runs GBMSimulator.step() every ``update_interval`` seconds -> PriceCache."""

    def __init__(
        self,
        price_cache: PriceCache,
        update_interval: float = 0.5,
        event_probability: float = 0.001,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._cache = price_cache
        self._interval = update_interval
        self._event_prob = event_probability
        self._rng = rng
        self._sim: GBMSimulator | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        tickers = list(dict.fromkeys(normalize_ticker(t) for t in tickers))  # dedupe, keep order
        self._sim = GBMSimulator(tickers, event_probability=self._event_prob, rng=self._rng)
        for ticker in tickers:
            self._seed_cache(ticker)  # first SSE frame has data immediately
        self._task = asyncio.create_task(self._run_loop(), name="simulator-loop")
        logger.info("Simulator started with %d tickers", len(tickers))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Simulator stopped")

    async def add_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if self._sim and ticker not in self._sim.get_tickers():
            self._sim.add_ticker(ticker)
            self._seed_cache(ticker)  # tradable immediately, no wait for next tick
            logger.info("Simulator: added %s", ticker)

    async def remove_ticker(self, ticker: str) -> None:
        ticker = normalize_ticker(ticker)
        if self._sim:
            self._sim.remove_ticker(ticker)
        self._cache.remove(ticker)
        logger.info("Simulator: removed %s", ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.get_tickers() if self._sim else []

    # ---- internals ----

    def _seed_cache(self, ticker: str) -> None:
        assert self._sim is not None
        price = self._sim.get_price(ticker)
        if price is not None:
            self._cache.update(ticker, price, session_open=self._sim.get_session_open(ticker))

    async def _run_loop(self) -> None:
        while True:
            try:
                if self._sim:
                    for ticker, price in self._sim.step().items():
                        self._cache.update(ticker, price)  # session_open carried forward
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
