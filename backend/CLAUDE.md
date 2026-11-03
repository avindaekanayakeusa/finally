# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import (
    PriceCache, PriceUpdate, MarketDataSource,
    create_market_data_source, create_stream_router, normalize_ticker,
)
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, `session_open`.
  - Tick-to-tick (flash animation): `change`, `change_percent`, `direction` ("up"/"down"/"flat").
  - Daily (watchlist "Chg %"): `day_change`, `day_change_percent` vs. `session_open` (`None` if unknown).
    `session_open` is the seed price for the simulator, `prev_day.close` for Massive.
  - `to_dict()` for JSON / SSE serialization (all of the above).

- **`normalize_ticker(raw)`** — `" aapl " -> "AAPL"`; raises `ValueError` on malformed input. Use it in API routes (return 422). Both sources also normalize internally.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None, session_open=None) -> PriceUpdate` (session_open carried forward if omitted)
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `snapshot() -> (version, dict)` — atomic read for the SSE loop
  - `remove(ticker)` — bumps the version if the ticker was present
  - `version` property — monotonic counter, increments on every update/remove (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set, otherwise `SimulatorDataSource`. `MASSIVE_POLL_INTERVAL` (seconds, default 15, min 1) tunes the Massive poll cadence.

- **What to track:** start the source with, and keep it synced to, **watchlist ∪ tickers with open positions** — otherwise a held position loses its price when removed from the watchlist. See `planning/MARKET_DATA_DESIGN.md` §12.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # New APIRouter per call
# Endpoint: GET /api/stream/prices (text/event-stream)
# Frames: "retry: 1000", then a full snapshot {ticker: PriceUpdate.to_dict()} whenever
# the cache version changes (checked every 0.5s), ": ping" heartbeat after 15s idle.
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Running Tests

```bash
uv run --extra dev pytest -v              # All tests
uv run --extra dev pytest --cov=app       # With coverage
uv run --extra dev ruff check app/ tests/ # Lint
```

## Demo

```bash
uv run market_data_demo.py   # Live terminal dashboard with simulated prices
```
