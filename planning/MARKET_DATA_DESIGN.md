# Market Data Backend — Detailed Design (v2)

Implementation guide for the FinAlly market data subsystem: the unified interface, the shared price cache, the GBM simulator, the Massive (Polygon.io) REST client, the SSE stream, and how the rest of the backend plugs into it.

**Relationship to existing docs**

- `planning/PLAN.md` §6 is the contract this design satisfies.
- `planning/MARKET_DATA_SUMMARY.md` describes what is already built in `backend/app/market/` (73 passing tests).
- `planning/archive/MARKET_DATA_DESIGN.md` is the v1 design that code was built from. **This document replaces it.** It keeps the v1 architecture and fixes the defects found while checking the code against PLAN.md and the real `massive` SDK. §15 lists every change, so an agent can apply them one by one.

All code lives under `backend/app/market/` unless a path says otherwise. Snippets are complete enough to paste in.

---

## Table of Contents

1. [Requirements Recap](#1-requirements-recap)
2. [Architecture & Data Flow](#2-architecture--data-flow)
3. [File Layout & Public API](#3-file-layout--public-api)
4. [Data Model — `models.py`](#4-data-model--modelspy)
5. [Price Cache — `cache.py`](#5-price-cache--cachepy)
6. [Unified Interface — `interface.py`](#6-unified-interface--interfacepy)
7. [Seed Data — `seed_prices.py`](#7-seed-data--seed_pricespy)
8. [GBM Simulator — `simulator.py`](#8-gbm-simulator--simulatorpy)
9. [Massive API Client — `massive_client.py`](#9-massive-api-client--massive_clientpy)
10. [Factory — `factory.py`](#10-factory--factorypy)
11. [SSE Stream — `stream.py`](#11-sse-stream--streampy)
12. [Application Integration](#12-application-integration)
13. [Testing](#13-testing)
14. [Error Handling & Edge Cases](#14-error-handling--edge-cases)
15. [Change List: Current Code → This Design](#15-change-list-current-code--this-design)
16. [Configuration Reference](#16-configuration-reference)

---

## 1. Requirements Recap

From PLAN.md, the market data layer must:

| # | Requirement | Where satisfied |
|---|-------------|-----------------|
| R1 | Two sources (simulator, Massive) behind one interface; selected by `MASSIVE_API_KEY` | §6, §10 |
| R2 | Simulator: GBM, ~500 ms ticks, per-ticker drift/vol, correlated moves, occasional 2–5 % shocks, realistic seeds | §8 |
| R3 | Massive: REST polling (not WebSocket), one call for all tickers, 15 s on free tier, 2–15 s on paid | §9 |
| R4 | Shared in-memory cache: latest price, previous price, timestamp per ticker | §5 |
| R5 | `GET /api/stream/prices` SSE at ~500 ms with ticker, price, previous price, timestamp, direction | §11 |
| R6 | Watchlist shows **daily change %** | §4 (`session_open`), §8, §9 |
| R7 | Tickers can be added/removed at runtime (REST or LLM) | §6, §12.3 |
| R8 | Trades fill instantly at the current cached price | §12.4 |
| R9 | Positions must stay priced even if their ticker leaves the watchlist | §12.3 |

R6 and R9 were not covered by v1. They are the main functional additions here.

---

## 2. Architecture & Data Flow

```
                 ┌──────────────────────────────┐
                 │  create_market_data_source() │  reads MASSIVE_API_KEY
                 └──────────────┬───────────────┘
                                │ returns one of
            ┌───────────────────┴────────────────────┐
            ▼                                        ▼
┌───────────────────────┐              ┌──────────────────────────┐
│  SimulatorDataSource  │              │    MassiveDataSource     │
│  asyncio task, 0.5 s  │              │  asyncio task, 15 s      │
│  GBMSimulator.step()  │              │  to_thread(get_snapshot) │
└───────────┬───────────┘              └────────────┬─────────────┘
            │  cache.update(ticker, price, ts, session_open)
            └──────────────────┬────────────────────┘
                               ▼
                 ┌──────────────────────────────┐
                 │  PriceCache  (threading.Lock)│
                 │  {ticker: PriceUpdate}       │
                 │  version: int                │
                 └───┬───────────┬──────────┬───┘
                     │           │          │
         snapshot()  │   get()   │          │ get_all()
                     ▼           ▼          ▼
          SSE /api/stream   POST /trade   GET /portfolio, /watchlist,
          /prices (0.5 s)   (fill price)  LLM context, snapshot task
```

Principles:

1. **Push into a cache; never pull from a source.** Sources write on their own schedule. Consumers read the cache and never know which source is active or how often it updates.
2. **One writer at a time.** Only one source is alive per process. The cache lock still guards against the Massive thread-pool call and readers on the event loop.
3. **`PriceUpdate` is the only type that leaves the package.** Downstream code never sees `numpy` arrays or `massive` SDK objects.
4. **Fail soft.** A bad tick, a bad snapshot, or a failed HTTP call is logged and skipped. The last known prices stay in the cache and the stream keeps running.

---

## 3. File Layout & Public API

```
backend/app/market/
├── __init__.py         # Re-exports the public API below
├── models.py           # PriceUpdate, normalize_ticker()
├── cache.py            # PriceCache
├── interface.py        # MarketDataSource (ABC)
├── seed_prices.py      # SEED_PRICES, TICKER_PARAMS, correlation constants
├── simulator.py        # GBMSimulator (math) + SimulatorDataSource (async wrapper)
├── massive_client.py   # MassiveDataSource
├── factory.py          # create_market_data_source()
└── stream.py           # create_stream_router() → GET /api/stream/prices
```

```python
# backend/app/market/__init__.py
"""Market data subsystem for FinAlly.

Public API:
    PriceUpdate               - Immutable price snapshot
    PriceCache                - Thread-safe in-memory price store
    MarketDataSource          - Abstract interface for data providers
    create_market_data_source - Factory: simulator or Massive, from env
    create_stream_router      - FastAPI router for the SSE endpoint
    normalize_ticker          - Canonical ticker formatting / validation
"""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate, normalize_ticker
from .stream import create_stream_router

__all__ = [
    "PriceUpdate",
    "PriceCache",
    "MarketDataSource",
    "create_market_data_source",
    "create_stream_router",
    "normalize_ticker",
]
```

Downstream code imports only from `app.market`. Submodules are internal.

---

## 4. Data Model — `models.py`

```python
"""Data models for market data."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def normalize_ticker(raw: str) -> str:
    """Return the canonical form of a ticker symbol ("  aapl " -> "AAPL").

    Raises ValueError for empty or malformed input. All market data entry
    points (sources, cache, API routes) use this so "aapl" and "AAPL" are
    never tracked as two tickers.
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
    previous_price: float                 # price at the previous update (tick-to-tick)
    timestamp: float = field(default_factory=time.time)  # Unix seconds
    session_open: float | None = None     # reference for daily change (see below)

    # --- tick-to-tick (drives flash animation) ---

    @property
    def change(self) -> float:
        return round(self.price - self.previous_price, 4)

    @property
    def change_percent(self) -> float:
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
        if not self.session_open:
            return None
        return round(self.price - self.session_open, 4)

    @property
    def day_change_percent(self) -> float | None:
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
```

### Two kinds of "change"

| Field | Meaning | Used for |
|-------|---------|----------|
| `previous_price`, `change`, `change_percent`, `direction` | vs. the **previous update** | Green/red price flash; sparkline colouring |
| `session_open`, `day_change`, `day_change_percent` | vs. a **daily reference price** | Watchlist "daily change %" column (PLAN §10) |

`session_open` depends on the source:

- **Simulator:** the ticker's price when it started being simulated (its seed price). This is a "since session start" change, which is the honest equivalent of a daily change for synthetic data.
- **Massive:** `prev_day.close` from the snapshot, which is the market definition of daily change.

Design choices kept from v1: `frozen=True` (safe to share across tasks), `slots=True` (many are created per second), derived values as properties (they can never disagree with `price`), and one serializer, `to_dict()`, for both SSE and REST.

Example:

```python
>>> u = PriceUpdate("AAPL", price=191.20, previous_price=191.05, timestamp=1730000000.0, session_open=190.00)
>>> u.direction, u.change, u.day_change_percent
('up', 0.15, 0.6316)
```

---

## 5. Price Cache — `cache.py`

```python
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
        self._version = 0

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
        with self._lock:
            return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
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
        with self._lock:
            if self._prices.pop(ticker, None) is not None:
                self._version += 1  # so SSE pushes a frame without the ticker

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def __len__(self) -> int:
        with self._lock:
            return len(self._prices)

    def __contains__(self, ticker: str) -> bool:
        with self._lock:
            return ticker in self._prices
```

### Notes

- **`threading.Lock`, not `asyncio.Lock`.** `asyncio.Lock` does not protect against OS threads, and the Massive SDK runs in `asyncio.to_thread`. Critical sections are a dict lookup plus an assignment, so holding the lock on the event loop costs microseconds.
- **Version counter.** The SSE loop runs every 500 ms, but Massive only changes data every 15 s. Comparing versions avoids re-sending identical frames. `snapshot()` reads the version and the prices under one lock acquisition, so a frame never mixes two versions.
- **`remove()` bumps the version.** In v1 it did not, so a removed ticker could stay on screen until the next price write. With Massive that could take up to 15 s.
- **`timestamp is None`, not `timestamp or ...`.** v1 treated a legitimate `0.0` as missing. This only matters in tests, but it is the correct check.
- **Memory** is O(number of tickers). The cache keeps no history. Sparklines are built in the frontend (PLAN §2), and the P&L chart uses `portfolio_snapshots` in SQLite.

---

## 6. Unified Interface — `interface.py`

```python
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
```

Interface rules:

| Rule | Why |
|------|-----|
| Methods are `async` even when the simulator does no I/O | A future source (e.g. a WebSocket feed) may need to await; callers don't change |
| No `get_price()` on the source | Forces every read through the cache, keeping one source of truth |
| `add_ticker` / `remove_ticker` are idempotent | Watchlist and LLM flows can call them without checking state first |
| Sources normalize tickers | v1 normalized in Massive but not in the simulator, so the two behaved differently |

---

## 7. Seed Data — `seed_prices.py`

Constants only, unchanged from the current code except for removing the unused `TSLA_CORR` alias. TSLA reuses `CROSS_GROUP_CORR` and has its own named constant only if we want to tune it separately.

```python
"""Seed prices and per-ticker parameters for the market simulator."""

SEED_PRICES: dict[str, float] = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, "AMZN": 185.00, "TSLA": 250.00,
    "NVDA": 800.00, "META": 500.00, "JPM": 195.00, "V": 280.00, "NFLX": 600.00,
}

# sigma = annualized volatility, mu = annualized drift
TICKER_PARAMS: dict[str, dict[str, float]] = {
    "AAPL":  {"sigma": 0.22, "mu": 0.05},
    "GOOGL": {"sigma": 0.25, "mu": 0.05},
    "MSFT":  {"sigma": 0.20, "mu": 0.05},
    "AMZN":  {"sigma": 0.28, "mu": 0.05},
    "TSLA":  {"sigma": 0.50, "mu": 0.03},   # high vol
    "NVDA":  {"sigma": 0.40, "mu": 0.08},   # high vol, strong drift
    "META":  {"sigma": 0.30, "mu": 0.05},
    "JPM":   {"sigma": 0.18, "mu": 0.04},   # low vol (bank)
    "V":     {"sigma": 0.17, "mu": 0.04},   # low vol (payments)
    "NFLX":  {"sigma": 0.35, "mu": 0.05},
}
DEFAULT_PARAMS: dict[str, float] = {"sigma": 0.25, "mu": 0.05}

# Random seed range for tickers not listed above
UNKNOWN_SEED_RANGE: tuple[float, float] = (50.0, 300.0)

CORRELATION_GROUPS: dict[str, set[str]] = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}
INTRA_TECH_CORR = 0.6
INTRA_FINANCE_CORR = 0.5
CROSS_GROUP_CORR = 0.3   # cross-sector, unknown tickers, and anything paired with TSLA
TSLA_CORR = 0.3          # TSLA is not in "tech" on purpose: it does its own thing
```

To add a well-known ticker with realistic behaviour, add it to `SEED_PRICES` and `TICKER_PARAMS` (and to a correlation group if it fits one). No code changes are needed.

---

## 8. GBM Simulator — `simulator.py`

Two classes:

- **`GBMSimulator`**: pure, synchronous maths. It holds prices and advances them one step at a time. It has no asyncio and no cache, so it is easy to unit test.
- **`SimulatorDataSource`**: the `MarketDataSource` implementation. It runs `step()` in an asyncio task and writes the results to the cache.

### 8.1 The maths

Each tick, every ticker evolves by exact-discretization GBM:

```
S(t+dt) = S(t) · exp( (μ − σ²/2)·dt + σ·√dt·Z )
```

- `dt` is the tick length as a fraction of a trading year: `0.5 s / (252 days × 6.5 h × 3600 s) ≈ 8.48e-8`.
- `Z` are **correlated** standard normals: `Z = L · ε`, where `ε ~ N(0, I)` and `L = cholesky(C)` for the pairwise correlation matrix `C`.
- `exp(·) > 0`, so prices can never reach zero or go negative.

Typical magnitudes, so you know what "normal" looks like:

| Quantity | AAPL (σ=0.22, $190) | TSLA (σ=0.50, $250) |
|----------|--------------------|--------------------|
| 1σ move per 0.5 s tick | ≈ $0.012 | ≈ $0.036 |
| 1σ move per simulated trading day | ≈ 1.4 % | ≈ 3.1 % |

Moves of a cent or two per tick are big enough to make the price flash and small enough to look realistic.

**Shock events.** After the GBM step, each ticker independently has `event_probability = 0.001` chance per tick of an extra ±2–5 % jump. At 2 ticks/s across 10 tickers, that is about one event every 50 s somewhere on the board.

**Correlation matrix.** `C[i][j]` comes from the sector rule below. Within-block correlations are 0.5–0.6 and every cross-block correlation is 0.3, so the matrix is positive-definite for any mix of tickers. This was checked numerically with the 10 defaults plus 40 unknown tickers. If someone later edits the constants and Cholesky fails, the simulator falls back to independent draws instead of crashing (see `_rebuild_cholesky`).

```
pair                     ρ
TSLA with anything       0.3
tech  × tech             0.6
fin   × fin              0.5
anything else            0.3
```

### 8.2 `GBMSimulator`

```python
"""GBM-based market simulator."""

from __future__ import annotations

import asyncio
import logging
import math
import random

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
    """Correlated Geometric Brownian Motion for a dynamic set of tickers."""

    TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600      # 5,896,800
    DEFAULT_DT = 0.5 / TRADING_SECONDS_PER_YEAR      # ≈ 8.48e-8

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
        # Injected RNG -> deterministic tests (np.random.default_rng(42))
        self._rng = rng or np.random.default_rng()

        self._tickers: list[str] = []
        self._prices: dict[str, float] = {}
        self._opens: dict[str, float] = {}           # session_open per ticker
        self._params: dict[str, dict[str, float]] = {}
        self._cholesky: np.ndarray | None = None

        for t in tickers:
            self._add_ticker_internal(t)
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

            if self._rng.random() < self._event_prob:
                shock = self._rng.uniform(0.02, 0.05) * (1 if self._rng.random() < 0.5 else -1)
                price *= 1 + shock
                logger.debug("Shock on %s: %+.1f%%", ticker, shock * 100)

            self._prices[ticker] = price          # keep full precision internally
            result[ticker] = round(price, 2)      # round only on the way out
        return result

    def add_ticker(self, ticker: str) -> None:
        if ticker in self._prices:
            return
        self._add_ticker_internal(ticker)
        self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker], self._opens[ticker], self._params[ticker]
        self._rebuild_cholesky()

    def get_price(self, ticker: str) -> float | None:
        return self._prices.get(ticker)

    def get_session_open(self, ticker: str) -> float | None:
        return self._opens.get(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)

    # ---- internals --------------------------------------------------------

    def _add_ticker_internal(self, ticker: str) -> None:
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
        """O(n²) rebuild on add/remove; n is small (< 50)."""
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
        if t1 == "TSLA" or t2 == "TSLA":
            return TSLA_CORR
        tech, fin = CORRELATION_GROUPS["tech"], CORRELATION_GROUPS["finance"]
        if t1 in tech and t2 in tech:
            return INTRA_TECH_CORR
        if t1 in fin and t2 in fin:
            return INTRA_FINANCE_CORR
        return CROSS_GROUP_CORR
```

Changes from the current code: an injectable `rng` for reproducible tests, one RNG instead of mixing `random` and `np.random`, full-precision internal prices (the current code already does this), `session_open` tracking, and a Cholesky fallback.

### 8.3 `SimulatorDataSource`

```python
class SimulatorDataSource(MarketDataSource):
    """Runs GBMSimulator.step() every `update_interval` seconds -> PriceCache."""

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
        for t in tickers:
            self._seed_cache(t)            # first SSE frame has data immediately
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
            self._seed_cache(ticker)       # tradable immediately, no wait for next tick
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
                        self._cache.update(ticker, price)   # session_open carried forward
            except Exception:
                logger.exception("Simulator step failed")
            await asyncio.sleep(self._interval)
```

`step()` for 10–50 tickers takes microseconds, so it runs on the event loop and doesn't need a thread.

### 8.4 Example: simulator in isolation

```python
import numpy as np
from app.market.simulator import GBMSimulator

sim = GBMSimulator(["AAPL", "MSFT", "JPM"], rng=np.random.default_rng(7))
for _ in range(3):
    print(sim.step())
# {'AAPL': 190.01, 'MSFT': 420.02, 'JPM': 194.99}
# {'AAPL': 190.0,  'MSFT': 419.99, 'JPM': 195.0}
# ...   (exact values depend on the seed)
```

---

## 9. Massive API Client — `massive_client.py`

### 9.1 Correctness issue in the current code (must fix)

The current `_poll_once` reads `snap.last_trade.timestamp`. In the real `massive` SDK (`massive.rest.models.trades.LastTrade`) **there is no `timestamp` attribute**. The fields are `sip_timestamp`, `participant_timestamp` and `trf_timestamp`, all in **nanoseconds**. Against the live API, every snapshot raises `AttributeError`, gets logged as "Skipping snapshot", and the cache stays empty. The unit tests pass only because `MagicMock` creates any attribute you ask for.

Verified against the installed SDK:

```python
>>> from massive.rest.models import TickerSnapshot
>>> s = TickerSnapshot.from_dict({"ticker": "AAPL",
...     "lastTrade": {"p": 190.5, "t": 1707580800123456789},
...     "prevDay": {"c": 189.0}, "updated": 1707580800123456789})
>>> s.last_trade.price, s.last_trade.sip_timestamp, s.prev_day.close
(190.5, 1707580800123456789, 189.0)
>>> hasattr(s.last_trade, "timestamp")
False
```

The archived `MASSIVE_API.md` also refers to `snap.day.previous_close` and `snap.day.change_percent`. Neither exists: `day` is a plain `Agg` (open/high/low/close/volume/vwap/timestamp). The real fields are `snap.prev_day.close`, `snap.todays_change` and `snap.todays_change_percent`.

### 9.2 Snapshot fields we use

`client.get_snapshot_all("stocks", tickers=[...])` → `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT,...` → `list[TickerSnapshot]`. One HTTP call covers every ticker, which is what keeps the free tier (5 req/min) usable.

| SDK attribute | JSON key | Unit | Use |
|---------------|----------|------|-----|
| `snap.ticker` | `ticker` | – | cache key |
| `snap.last_trade.price` | `lastTrade.p` | USD | **primary price** |
| `snap.last_trade.sip_timestamp` | `lastTrade.t` | **ns** | price timestamp |
| `snap.min.close` | `min.c` | USD | fallback price (latest minute bar) |
| `snap.day.close` | `day.c` | USD | fallback price |
| `snap.prev_day.close` | `prevDay.c` | USD | **`session_open`** (daily reference); last-resort price |
| `snap.updated` | `updated` | **ns** | fallback timestamp |

The fallback chain matters: `last_trade` can be missing on some plans and early in the morning (snapshots reset at midnight ET and refill from about 4 am ET), and an unknown ticker is simply absent from the response.

### 9.3 Implementation

```python
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

    Pure function, no I/O: unit-test it with TickerSnapshot.from_dict(...).
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
        if candidate:          # skips None and 0
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
    On failures the interval backs off exponentially (capped) and resets
    on the next success.
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
        await self._poll_once()                      # data before first SSE frame
        self._task = asyncio.create_task(self._poll_loop(), name="massive-poller")
        logger.info("Massive poller started: %d tickers, %.1fs interval",
                    len(self._tickers), self._interval)

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
        # Price it now rather than up to 15 s later, so the user can trade at once.
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
        return min(self._interval * 2 ** self._consecutive_failures, self.MAX_BACKOFF)

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._next_delay())
            await self._poll_once()

    async def _poll_once(self, only: list[str] | None = None) -> None:
        tickers = list(only or self._tickers)        # copy: list may change mid-call
        if not tickers or not self._client:
            return
        try:
            snapshots = await asyncio.to_thread(self._fetch_snapshots, tickers)
        except AuthError as e:
            self._consecutive_failures += 1
            logger.error("Massive auth failed (check MASSIVE_API_KEY): %s", e)
            return
        except BadResponse as e:                    # 403 plan limits, 429 rate limit, 5xx
            self._consecutive_failures += 1
            logger.warning("Massive bad response: %s", e)
            return
        except Exception as e:                       # network, timeouts, JSON
            self._consecutive_failures += 1
            logger.warning("Massive poll failed: %s", e)
            return

        self._consecutive_failures = 0
        tracked = set(self._tickers)                 # ignore tickers removed meanwhile
        updated = 0
        for snap in snapshots:
            parsed = parse_snapshot(snap)
            if parsed is None:
                logger.debug("Massive: unusable snapshot for %s", getattr(snap, "ticker", "?"))
                continue
            ticker, price, ts, session_open = parsed
            if ticker not in tracked:
                continue
            self._cache.update(ticker, price, timestamp=ts, session_open=session_open)
            updated += 1

        missing = set(tickers) - {getattr(s, "ticker", None) for s in snapshots}
        if missing:
            logger.info("Massive: no data for %s (unknown symbol or no trades yet)",
                        ", ".join(sorted(missing)))
        logger.debug("Massive poll: %d/%d updated", updated, len(tickers))

    def _fetch_snapshots(self, tickers: list[str]) -> list:
        """Blocking SDK call - always run via asyncio.to_thread."""
        assert self._client is not None
        return self._client.get_snapshot_all(
            market_type=SnapshotMarketType.STOCKS,
            tickers=tickers,
        )
```

### 9.4 Behaviour notes

- **Cache timestamps.** We store the exchange trade time rather than "now". After hours the price doesn't change. The version still increments on each write, so SSE re-sends identical prices every 15 s with `direction: "flat"`. That is correct: no flash, and the frontend can show the trade age.
- **Removal race.** A poll that started before `remove_ticker` can return data for the removed ticker. The `tracked` filter stops it reappearing in the cache.
- **Thread safety.** Only `_fetch_snapshots` runs in the worker thread. Cache writes happen back on the event loop after `await`, so the lock is a safety net rather than something we rely on.
- **Request size.** The tickers go in the query string. 50 tickers is about 300 characters, well within limits. Above about 200 tickers, chunk the list into several calls.
- **SDK retries.** `RESTClient` retries 5xx responses internally (3 by default). Our backoff handles anything that is still failing after that.

### 9.5 Example: one-off manual check

```python
# uv run python -c "..."  with MASSIVE_API_KEY exported
from massive import RESTClient
from app.market.massive_client import parse_snapshot

client = RESTClient()  # reads MASSIVE_API_KEY
for snap in client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT", "NOTREAL"]):
    print(parse_snapshot(snap))
# ('AAPL', 227.48, 1730493599.871, 225.91)
# ('MSFT', 410.37, 1730493599.512, 406.35)
#  -> NOTREAL simply absent from the response
```

---

## 10. Factory — `factory.py`

```python
"""Factory for creating market data sources."""

from __future__ import annotations

import logging
import os

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_client import MassiveDataSource
from .simulator import SimulatorDataSource

logger = logging.getLogger(__name__)


def _float_env(name: str, default: float, minimum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(float(raw), minimum)
    except ValueError:
        logger.warning("Ignoring invalid %s=%r; using %s", name, raw, default)
        return default


def create_market_data_source(price_cache: PriceCache) -> MarketDataSource:
    """MASSIVE_API_KEY set and non-empty -> MassiveDataSource; else simulator.

    Returns an unstarted source; caller must `await source.start(tickers)`.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        interval = _float_env("MASSIVE_POLL_INTERVAL", default=15.0, minimum=1.0)
        logger.info("Market data source: Massive API (poll every %.1fs)", interval)
        return MassiveDataSource(api_key=api_key, price_cache=price_cache, poll_interval=interval)

    logger.info("Market data source: GBM simulator")
    return SimulatorDataSource(price_cache=price_cache)
```

`MASSIVE_POLL_INTERVAL` is a new optional variable. It lets paid-tier users choose 2–5 s without code changes (PLAN §6: "Paid tiers: poll every 2-15 seconds"). Add it to `.env.example`, commented out.

---

## 11. SSE Stream — `stream.py`

### 11.1 Wire contract

- `GET /api/stream/prices`, `Content-Type: text/event-stream`
- First frame: `retry: 1000` (the browser reconnects 1 s after a drop)
- Then one `data:` frame each time the cache version changes, checked every 500 ms. Each frame is a **full snapshot**: an object keyed by ticker. Full snapshots make the client simple (a reconnect needs no resync) and stay small (about 2.5 KB for 10 tickers).
- A comment heartbeat (`: ping`) every 15 s with no data, so proxies and load balancers don't close a quiet connection. This matters in Massive mode outside market hours.

```
retry: 1000

data: {"AAPL":{"ticker":"AAPL","price":190.12,"previous_price":190.09,"timestamp":1730480000.51,"change":0.03,"change_percent":0.0158,"direction":"up","session_open":190.0,"day_change":0.12,"day_change_percent":0.0632},"MSFT":{...}}

data: {...}

: ping

```

A ticker missing from a frame has been removed. The frontend should drop it from the watchlist state.

### 11.2 Implementation

v1 registered the route on a **module-level** router inside the factory, so calling `create_stream_router()` twice (as tests do) added the route twice. The router is now created inside the factory.

```python
"""SSE streaming endpoint for live price updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",   # disable proxy buffering (nginx etc.)
}


def create_stream_router(
    price_cache: PriceCache,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> APIRouter:
    router = APIRouter(prefix="/api/stream", tags=["streaming"])

    @router.get("/prices")
    async def stream_prices(request: Request) -> StreamingResponse:
        return StreamingResponse(
            generate_price_events(price_cache, request, interval, heartbeat),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    return router


async def generate_price_events(
    price_cache: PriceCache,
    request: Request,
    interval: float = 0.5,
    heartbeat: float = 15.0,
) -> AsyncGenerator[str, None]:
    """Yield SSE frames until the client disconnects."""
    client = request.client.host if request.client else "unknown"
    logger.info("SSE connected: %s", client)
    yield "retry: 1000\n\n"

    last_version = -1
    last_sent = time.monotonic()
    try:
        while not await request.is_disconnected():
            version, prices = price_cache.snapshot()
            now = time.monotonic()
            if version != last_version:
                last_version = version
                payload = {t: u.to_dict() for t, u in prices.items()}
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                last_sent = now
            elif now - last_sent >= heartbeat:
                yield ": ping\n\n"
                last_sent = now
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("SSE disconnected: %s", client)
```

Notes:

- An empty cache (empty watchlist) sends `data: {}` once rather than nothing, so the frontend can tell "connected, no tickers" apart from "still connecting".
- Every connected client polls the shared cache independently. With a single user this costs nothing. For many clients, a broadcast (one producer task fanning out to per-client queues) would be the next step, and the interface would not change.

### 11.3 Frontend consumption (reference for the frontend agent)

```ts
// frontend: lib/usePriceStream.ts
type PriceUpdate = {
  ticker: string; price: number; previous_price: number; timestamp: number;
  change: number; change_percent: number; direction: "up" | "down" | "flat";
  session_open: number | null; day_change: number | null; day_change_percent: number | null;
};
type Status = "connected" | "reconnecting" | "disconnected";

export function connectPrices(
  onPrices: (p: Record<string, PriceUpdate>) => void,
  onStatus: (s: Status) => void,
): () => void {
  const es = new EventSource("/api/stream/prices");
  es.onopen = () => onStatus("connected");
  es.onmessage = (e) => onPrices(JSON.parse(e.data));
  es.onerror = () =>
    onStatus(es.readyState === EventSource.CLOSED ? "disconnected" : "reconnecting");
  return () => es.close();
}
```

Sparklines: on each frame, append `price` to a per-ticker ring buffer (about 120 points ≈ 1 min) **only when `timestamp` changed**. This avoids flat duplicate points from Massive heartbeats. Flash: when `direction !== "flat"`, add a `flash-up` or `flash-down` class and remove it after about 500 ms.

---

## 12. Application Integration

This section covers `backend/app/main.py` and the other route modules. They are not part of the market package, but they define how it is used.

### 12.1 Lifespan

```python
# backend/app/main.py
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db, get_tracked_tickers        # owned by the backend/DB agent
from app.market import PriceCache, create_market_data_source, create_stream_router

price_cache = PriceCache()   # module-level so routers can be built before startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                                      # lazy create + seed (PLAN §7)
    source = create_market_data_source(price_cache)
    await source.start(get_tracked_tickers())      # watchlist ∪ open positions
    app.state.price_cache = price_cache
    app.state.market_source = source
    try:
        yield
    finally:
        await source.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(create_stream_router(price_cache))   # include at import time
# app.include_router(portfolio_router); app.include_router(watchlist_router); ...
# app.mount("/", StaticFiles(directory="static", html=True))  # mount LAST
```

Include routers at import time, not inside `lifespan`. Routes added after startup work in Starlette, but they don't appear in OpenAPI and they make ordering against the static mount fragile.

```python
# backend/app/deps.py
from fastapi import Request
from app.market import MarketDataSource, PriceCache

def get_price_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache

def get_market_source(request: Request) -> MarketDataSource:
    return request.app.state.market_source
```

### 12.2 What the source tracks: watchlist ∪ positions

PLAN §6 says the stream covers "all tickers known to the system". The source must track **every ticker on the watchlist and every ticker with a non-zero position**. Otherwise a held position loses its price when its ticker is removed from the watchlist, and portfolio value, the heatmap and sells all break.

```python
# backend/app/db/queries.py  (sketch)
def get_tracked_tickers(user_id: str = "default") -> list[str]:
    rows = conn.execute(
        """
        SELECT ticker FROM watchlist WHERE user_id = ?
        UNION
        SELECT ticker FROM positions WHERE user_id = ? AND quantity > 0
        """,
        (user_id, user_id),
    ).fetchall()
    return [r[0] for r in rows]
```

One helper keeps the source in sync after any change (watchlist add/remove, trade, LLM action):

```python
# backend/app/market_sync.py
from app.db import get_tracked_tickers
from app.market import MarketDataSource

async def sync_tracked_tickers(source: MarketDataSource) -> None:
    """Reconcile the source's ticker set with DB truth. Idempotent."""
    wanted = set(get_tracked_tickers())
    current = set(source.get_tickers())
    for t in sorted(wanted - current):
        await source.add_ticker(t)
    for t in sorted(current - wanted):
        await source.remove_ticker(t)
```

Note: the SSE payload then includes held-but-unwatched tickers. The frontend renders the **watchlist** from `GET /api/watchlist` and looks up prices in the SSE map, so extra tickers in the map are harmless and are exactly what the positions table needs.

### 12.3 Watchlist routes

```python
# backend/app/routes/watchlist.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache, normalize_ticker
from app.market_sync import sync_tracked_tickers

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    ticker: str


@router.get("")
async def list_watchlist(cache: PriceCache = Depends(get_price_cache)):
    out = []
    for ticker in db.get_watchlist():                  # ordered by added_at
        u = cache.get(ticker)
        out.append({"ticker": ticker, **(u.to_dict() if u else {"price": None})})
    return out


@router.post("", status_code=201)
async def add_to_watchlist(
    body: WatchlistAdd,
    source: MarketDataSource = Depends(get_market_source),
    cache: PriceCache = Depends(get_price_cache),
):
    try:
        ticker = normalize_ticker(body.ticker)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.add_watchlist(ticker)                            # INSERT OR IGNORE
    await sync_tracked_tickers(source)
    u = cache.get(ticker)
    return {"ticker": ticker, "price": u.price if u else None}


@router.delete("/{ticker}", status_code=204)
async def remove_from_watchlist(
    ticker: str,
    source: MarketDataSource = Depends(get_market_source),
):
    db.remove_watchlist(normalize_ticker(ticker))
    await sync_tracked_tickers(source)                  # keeps it if a position exists
```

### 12.4 Trade execution reads the cache

```python
price = cache.get_price(ticker)
if price is None:
    # Simulator: cannot happen for a tracked ticker (seeded on add).
    # Massive: unknown symbol, or not yet returned by the API.
    raise HTTPException(400, f"No live price for {ticker} yet. Add it to the watchlist and retry.")
# ... validate cash/shares, fill at `price`, write trade + position, then:
await sync_tracked_tickers(source)   # a buy of an unwatched ticker starts tracking;
                                     # selling to zero an unwatched one stops it
```

Buying a ticker that isn't tracked yet (for example via the trade bar or the LLM) should first call `await source.add_ticker(ticker)`, then read the price. With the simulator the price is available at once. With Massive, `add_ticker` does an immediate poll (§9.3), so the price is available at once if the symbol exists.

### 12.5 Other consumers

| Consumer | Call |
|----------|------|
| `GET /api/portfolio` | `cache.get_price(t)` per position; fall back to `avg_cost` if `None` and flag it |
| Snapshot task (30 s) | `cache.get_all()` once, then value all positions with it |
| LLM context | `cache.get_all()` → `{t: u.to_dict()}` for watchlist and positions |
| LLM watchlist actions | same code path as §12.3, then `sync_tracked_tickers` |

---

## 13. Testing

Current suite: 73 tests in `backend/tests/market/`. Keep them, and add or adjust the following. Run with `uv run --extra dev pytest`.

### 13.1 Massive: test against real SDK models, not bare `MagicMock`

This is the change that would have caught §9.1.

```python
# tests/market/test_massive.py
from massive.rest.models import TickerSnapshot
from app.market.massive_client import parse_snapshot, MassiveDataSource
from app.market.cache import PriceCache
from unittest.mock import MagicMock, patch


def snap(ticker, price=None, t_ns=None, prev_close=None, minute_close=None, updated=None):
    d = {"ticker": ticker}
    if price is not None:
        d["lastTrade"] = {"p": price, **({"t": t_ns} if t_ns else {})}
    if prev_close is not None:
        d["prevDay"] = {"c": prev_close}
    if minute_close is not None:
        d["min"] = {"c": minute_close}
    if updated is not None:
        d["updated"] = updated
    return TickerSnapshot.from_dict(d)


def test_parse_uses_last_trade_and_ns_timestamp():
    assert parse_snapshot(snap("AAPL", 190.5, t_ns=1_707_580_800_500_000_000, prev_close=189.0)) == (
        "AAPL", 190.5, 1_707_580_800.5, 189.0)

def test_parse_falls_back_to_minute_close_and_updated():
    t, p, ts, so = parse_snapshot(snap("MSFT", minute_close=410.0, updated=1_000_000_000_000_000_000))
    assert (t, p, ts, so) == ("MSFT", 410.0, 1_000_000_000.0, None)

def test_parse_returns_none_without_any_price():
    assert parse_snapshot(snap("ZZZZ")) is None


async def test_poll_once_writes_session_open():
    cache = PriceCache()
    src = MassiveDataSource("k", cache, poll_interval=60)
    src._tickers, src._client = ["AAPL"], MagicMock()
    with patch.object(src, "_fetch_snapshots",
                      return_value=[snap("AAPL", 191.0, t_ns=1, prev_close=190.0)]):
        await src._poll_once()
    u = cache.get("AAPL")
    assert u.price == 191.0 and u.session_open == 190.0
    assert round(u.day_change_percent, 4) == 0.5263

async def test_removed_ticker_not_resurrected_by_inflight_poll():
    cache = PriceCache()
    src = MassiveDataSource("k", cache, poll_interval=60)
    src._tickers, src._client = ["AAPL"], MagicMock()

    def fetch(_tickers):
        src._tickers = []            # simulate remove_ticker during the HTTP call
        return [snap("AAPL", 191.0)]
    with patch.object(src, "_fetch_snapshots", side_effect=fetch):
        await src._poll_once()
    assert "AAPL" not in cache

async def test_backoff_grows_and_resets():
    src = MassiveDataSource("k", PriceCache(), poll_interval=15)
    src._tickers, src._client = ["AAPL"], MagicMock()
    with patch.object(src, "_fetch_snapshots", side_effect=RuntimeError("down")):
        await src._poll_once(); await src._poll_once()
    assert src._next_delay() == 60
    with patch.object(src, "_fetch_snapshots", return_value=[]):
        await src._poll_once()
    assert src._next_delay() == 15
```

### 13.2 Cache

```python
def test_timestamp_zero_is_respected():
    assert PriceCache().update("AAPL", 1.0, timestamp=0.0).timestamp == 0.0

def test_remove_bumps_version():
    c = PriceCache(); c.update("AAPL", 1.0); v = c.version
    c.remove("AAPL"); assert c.version == v + 1
    c.remove("AAPL"); assert c.version == v + 1   # no-op remove doesn't bump

def test_session_open_carried_forward():
    c = PriceCache()
    c.update("AAPL", 190.0, session_open=189.0)
    assert c.update("AAPL", 191.0).session_open == 189.0

def test_concurrent_writers():
    import threading
    c = PriceCache()
    ths = [threading.Thread(target=lambda: [c.update("AAPL", float(i)) for i in range(1000)])
           for _ in range(8)]
    [t.start() for t in ths]; [t.join() for t in ths]
    assert c.version == 8000
```

### 13.3 Simulator

```python
import numpy as np
from app.market.simulator import GBMSimulator
from app.market.seed_prices import SEED_PRICES

DEFAULTS = list(SEED_PRICES)

def test_deterministic_with_seeded_rng():
    a = GBMSimulator(DEFAULTS, rng=np.random.default_rng(1))
    b = GBMSimulator(DEFAULTS, rng=np.random.default_rng(1))
    assert [a.step() for _ in range(50)] == [b.step() for _ in range(50)]

def test_cholesky_ok_for_defaults_plus_many_unknowns():
    sim = GBMSimulator(DEFAULTS + [f"X{i}" for i in range(40)])
    assert sim._cholesky is not None and sim._cholesky.shape == (50, 50)

def test_empirical_correlation_tech_vs_finance():
    sim = GBMSimulator(["AAPL", "MSFT", "JPM"], event_probability=0, rng=np.random.default_rng(0))
    prev = {t: sim.get_price(t) for t in sim.get_tickers()}
    rets = {t: [] for t in prev}
    for _ in range(20_000):
        sim.step()
        for t in prev:
            p = sim.get_price(t); rets[t].append(np.log(p / prev[t])); prev[t] = p
    tech = np.corrcoef(rets["AAPL"], rets["MSFT"])[0, 1]
    cross = np.corrcoef(rets["AAPL"], rets["JPM"])[0, 1]
    assert 0.55 < tech < 0.65 and 0.25 < cross < 0.35

def test_session_open_is_seed():
    sim = GBMSimulator(["AAPL"]); sim.step()
    assert sim.get_session_open("AAPL") == SEED_PRICES["AAPL"]
```

`SimulatorDataSource` tests: also assert that `add_ticker(" pypl ")` results in `"PYPL"` in both `get_tickers()` and the cache.

### 13.4 SSE generator (no server needed)

Drive the generator directly with a fake request. This avoids the difficulty of streaming an infinite response through `TestClient`.

```python
# tests/market/test_stream.py
import json
from app.market.cache import PriceCache
from app.market.stream import generate_price_events, create_stream_router


class FakeRequest:
    def __init__(self, polls_before_disconnect: int):
        self._n = polls_before_disconnect
        self.client = None
    async def is_disconnected(self):
        self._n -= 1
        return self._n < 0


async def collect(cache, polls, **kw):
    return [f async for f in generate_price_events(cache, FakeRequest(polls), interval=0, **kw)]


async def test_first_frame_is_retry_then_data():
    c = PriceCache(); c.update("AAPL", 190.0)
    frames = await collect(c, polls=1)
    assert frames[0] == "retry: 1000\n\n"
    body = json.loads(frames[1].removeprefix("data: "))
    assert body["AAPL"]["price"] == 190.0 and body["AAPL"]["direction"] == "flat"

async def test_no_duplicate_frames_without_changes():
    c = PriceCache(); c.update("AAPL", 190.0)
    frames = await collect(c, polls=5, heartbeat=999)
    assert sum(f.startswith("data:") for f in frames) == 1

async def test_heartbeat_when_idle():
    c = PriceCache(); c.update("AAPL", 190.0)
    frames = await collect(c, polls=3, heartbeat=0)
    assert ": ping\n\n" in frames

def test_router_factory_is_reentrant():
    r1, r2 = create_stream_router(PriceCache()), create_stream_router(PriceCache())
    assert len(r1.routes) == len(r2.routes) == 1
```

### 13.5 Optional live smoke test

Mark it `@pytest.mark.skipif(not os.getenv("MASSIVE_API_KEY"), ...)`. It starts `MassiveDataSource` with `["AAPL"]` and asserts that `cache.get("AAPL")` is not `None` after `start()`. It is not run in CI, but it is the one test that exercises the real SDK.

---

## 14. Error Handling & Edge Cases

| Situation | Behaviour |
|-----------|-----------|
| Empty watchlist at startup | Sources start with `[]`. Simulator steps return `{}`, Massive skips calls. SSE sends `data: {}` once. |
| Exception inside `GBMSimulator.step()` | Logged with traceback. Loop sleeps and continues. Cache keeps last prices. |
| Cholesky fails (bad constants) | Logged. Simulator falls back to uncorrelated moves. |
| Massive 401 / `AuthError` | Logged as error with a hint about `MASSIVE_API_KEY`. Backoff up to 120 s. No prices appear. The header dot stays green because SSE is connected, so the watchlist should show "—" for `price: null`. |
| Massive 429 / 403 / 5xx | Logged as warning. Exponential backoff (15→30→60→120 s). Last prices stay in the cache. |
| Unknown symbol (Massive) | Absent from the response and logged at info. No cache entry, so trades return 400 with a clear message. The frontend shows "—". |
| Unknown symbol (simulator) | Every syntactically valid symbol gets a random seed price ($50–300) and default parameters. This is intentional for the demo. |
| Malformed ticker (`"$$$"`, `""`) | `normalize_ticker` raises `ValueError` → route returns 422. Sources never see it. |
| Remove ticker while poll in flight | Filtered by the `tracked` set (§9.3). |
| Ticker removed from watchlist but still held | Kept by `sync_tracked_tickers` (§12.2). |
| Client disconnects from SSE | `is_disconnected()` ends the generator. Starlette cancels it on shutdown. Both paths log. |
| App shutdown | `lifespan` `finally:` awaits `source.stop()`. Task cancelled and awaited. Idempotent. |
| Market closed (Massive) | Last trade price persists. `direction` is `"flat"`. `day_change_percent` is vs. the previous close. |

---

## 15. Change List: Current Code → This Design

Apply these in order. Each one is small and independently testable.

| # | File | Change | Severity |
|---|------|--------|----------|
| 1 | `massive_client.py` | Replace `snap.last_trade.timestamp / 1000` with `parse_snapshot()` (uses `sip_timestamp` in **ns**, price fallbacks, `prev_day.close`). | **Critical**: Massive mode fails against the real API |
| 2 | `tests/market/test_massive.py` | Build snapshots with `TickerSnapshot.from_dict` instead of bare `MagicMock`; add tests from §13.1. | High |
| 3 | `models.py`, `cache.py` | Add `session_open` field and `day_change` / `day_change_percent`; cache accepts and carries forward `session_open`. | High (PLAN daily change %) |
| 4 | `simulator.py`, `massive_client.py` | Supply `session_open` (seed price / `prev_day.close`). | High |
| 5 | App layer | `get_tracked_tickers()` = watchlist ∪ positions, and `sync_tracked_tickers()`. | High (positions lose price) |
| 6 | `stream.py` | Create `APIRouter` inside the factory; use `cache.snapshot()`; add heartbeat; expose `generate_price_events`. | Medium |
| 7 | `cache.py` | `timestamp is None`; `remove()` bumps version; `version` read under lock; add `snapshot()`. | Medium |
| 8 | `models.py` + both sources | `normalize_ticker()` used by both sources (the simulator does not normalize today). | Medium |
| 9 | `massive_client.py` | Typed exception handling + exponential backoff; immediate poll on `add_ticker`; in-flight removal guard. | Medium |
| 10 | `factory.py`, `.env.example` | `MASSIVE_POLL_INTERVAL` env var. | Low |
| 11 | `simulator.py` | Injectable `np.random.Generator`; one RNG; Cholesky fallback. | Low |
| 12 | `seed_prices.py` | Add `UNKNOWN_SEED_RANGE`. | Low |
| 13 | `planning/archive/MASSIVE_API.md` | Note that `day.previous_close` / `day.change_percent` / `last_trade.timestamp` do not exist in the SDK (see §9.2). | Docs |

Compatibility: `PriceUpdate.to_dict()` only **adds** keys, so any frontend code written against v1 keeps working. All public signatures stay the same apart from new optional keyword arguments.

---

## 16. Configuration Reference

| Setting | Where | Default | Notes |
|---------|-------|---------|-------|
| `MASSIVE_API_KEY` | env | empty | Non-empty → Massive; else simulator |
| `MASSIVE_POLL_INTERVAL` | env | `15` s | Minimum 1 s. Free tier needs ≥ 12 s (5 req/min) plus headroom for `add_ticker` polls |
| `update_interval` | `SimulatorDataSource` | `0.5` s | Simulator tick |
| `event_probability` | `SimulatorDataSource` / `GBMSimulator` | `0.001` | Per ticker per tick |
| `dt` | `GBMSimulator` | `≈ 8.48e-8` | 0.5 s as a fraction of a trading year |
| `MAX_BACKOFF` | `MassiveDataSource` | `120` s | Cap for failure backoff |
| SSE `interval` | `create_stream_router` | `0.5` s | Cache check cadence |
| SSE `heartbeat` | `create_stream_router` | `15` s | Comment frame when idle |
| SSE `retry` | `generate_price_events` | `1000` ms | Browser reconnect delay |
