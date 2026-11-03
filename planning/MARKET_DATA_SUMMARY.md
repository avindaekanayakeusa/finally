# Market Data Backend — Summary

**Status:** Complete, tested, reviewed. Updated to design v2 (`planning/MARKET_DATA_DESIGN.md`), all §15 change-list items applied except #5 (app layer, owned by the backend/DB work).

## What Was Built

A complete market data subsystem in `backend/app/market/` (8 modules, ~500 lines) providing live price simulation and real market data via a unified interface.

### Architecture

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key needed)
└── MassiveDataSource    →  Polygon.io REST poller (when MASSIVE_API_KEY set)
        │
        ▼
   PriceCache (thread-safe, in-memory)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

### Modules

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate` — immutable frozen dataclass (ticker, price, previous_price, timestamp, session_open; change, direction, day_change, day_change_percent); `normalize_ticker()` |
| `interface.py` | `MarketDataSource` — abstract base class defining `start/stop/add_ticker/remove_ticker/get_tickers` |
| `cache.py` | `PriceCache` — thread-safe price store with version counter and atomic `snapshot()` for SSE change detection |
| `seed_prices.py` | Realistic seed prices, per-ticker GBM params (drift/volatility), correlation groups |
| `simulator.py` | `GBMSimulator` (Geometric Brownian Motion with Cholesky-correlated moves) + `SimulatorDataSource` |
| `massive_client.py` | `parse_snapshot()` + `MassiveDataSource` — REST polling client (ns timestamps, price fallbacks, `prev_day.close` as session open, exponential backoff, immediate poll on add) |
| `factory.py` | `create_market_data_source()` — selects simulator or Massive based on `MASSIVE_API_KEY`; `MASSIVE_POLL_INTERVAL` sets the poll interval |
| `stream.py` | `create_stream_router()` / `generate_price_events()` — SSE endpoint with version-based change detection and 15 s heartbeat |

### Key Design Decisions

- **Strategy pattern** — both data sources implement the same ABC; downstream code is source-agnostic
- **PriceCache as single point of truth** — producers write, consumers read; no direct coupling
- **GBM with correlated moves** — Cholesky decomposition of sector-based correlation matrix; tech stocks correlate at 0.6, finance at 0.5, cross-sector at 0.3
- **Random shock events** — ~0.1% chance per tick per ticker of a 2-5% move for visual drama
- **SSE over WebSockets** — simpler, one-way push, universal browser support

## Test Suite

**136 tests, all passing.** 7 test modules in `backend/tests/market/`. Overall coverage: 98%.

| Module | Covers |
|--------|--------|
| test_models.py | `PriceUpdate` (tick + daily change), `normalize_ticker` |
| test_cache.py | cache semantics, `session_open` carry-forward, `snapshot()`, remove/version, concurrency |
| test_simulator.py | GBM maths, seeded determinism, Cholesky (50 tickers + fallback), empirical correlation, shocks |
| test_simulator_source.py | async lifecycle, normalization/dedupe, session open in cache |
| test_factory.py | source selection, `MASSIVE_POLL_INTERVAL` parsing |
| test_massive.py | `parse_snapshot` against real SDK `TickerSnapshot` models, polling, backoff, in-flight removal guard |
| test_stream.py | SSE frames, dedupe, heartbeat, removal frames, router re-entrancy |

## Code Review & Fixes Applied

A comprehensive code review identified 7 issues. All were resolved:

1. **pyproject.toml build config** — added `[tool.hatch.build.targets.wheel] packages = ["app"]`
2. **Lazy imports removed** — `massive` is a core dependency; imports moved to top level
3. **SSE return type fixed** — `_generate_events` annotated as `AsyncGenerator[str, None]`
4. **Public `get_tickers()`** — added to `GBMSimulator` to avoid private attribute access
5. **Correlation constants cleaned up** — removed unused `DEFAULT_CORR`, consolidated into `CROSS_GROUP_CORR`
6. **Unused test imports removed** — `pytest`, `math`, `asyncio` cleaned from 4 test files
7. **Massive test mocks fixed** — `source._client` set in tests, patches target correct names

## Demo

A Rich terminal demo is available at `backend/market_data_demo.py`:

```bash
cd backend
uv run market_data_demo.py
```

Displays a live-updating dashboard with all 10 tickers, sparklines, color-coded direction arrows, and an event log for notable price moves. Runs 60 seconds or until Ctrl+C.

## Usage for Downstream Code

```python
from app.market import PriceCache, create_market_data_source

# Startup
cache = PriceCache()
source = create_market_data_source(cache)  # Reads MASSIVE_API_KEY
await source.start(["AAPL", "GOOGL", "MSFT", ...])

# Read prices
update = cache.get("AAPL")          # PriceUpdate or None
price = cache.get_price("AAPL")     # float or None
all_prices = cache.get_all()        # dict[str, PriceUpdate]

# Dynamic watchlist
await source.add_ticker("TSLA")
await source.remove_ticker("GOOGL")

# Shutdown
await source.stop()
```
