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

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, `session_open`, plus properties `change`, `change_percent`, `direction` ("up"/"down"/"flat") (tick-to-tick, drives the flash), `day_change`, `day_change_percent` (vs. `session_open`, drives the watchlist daily change %; `None` if unknown), and `to_dict()` for JSON serialization.

- **`normalize_ticker(raw) -> str`** — `" aapl "` -> `"AAPL"`; raises `ValueError` for malformed symbols (map to HTTP 422). Both sources normalize internally.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None, session_open=None) -> PriceUpdate` (`session_open` carried forward if omitted)
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `snapshot() -> (version, dict[str, PriceUpdate])` — atomic read, used by SSE
  - `remove(ticker)` — bumps version so SSE pushes a frame without the ticker
  - `version` property — monotonic counter, increments on every update/remove (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set (poll interval from `MASSIVE_POLL_INTERVAL`, default 15 s), otherwise `SimulatorDataSource`.

**Track watchlist ∪ open positions.** The app layer must keep the source tracking every watchlist ticker *and* every ticker with a non-zero position, or held positions lose their price when removed from the watchlist. See `planning/MARKET_DATA_DESIGN.md` §12.2 (`get_tracked_tickers()` / `sync_tracked_tickers()`).

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
# Frames: "retry: 1000", then a full {ticker: PriceUpdate.to_dict()} snapshot on each
# cache version change (checked every 0.5 s), ": ping" heartbeat every 15 s when idle.
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
