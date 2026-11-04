# Market Data Backend — Summary

**Status:** Complete. Implements `planning/MARKET_DATA_DESIGN.md` (v2). 175 tests passing, 99% coverage.

## What Was Built

A complete market data subsystem in `backend/app/market/` (8 modules) providing live price simulation and real market data via a unified interface.

### Architecture

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key needed)
└── MassiveDataSource    →  Massive/Polygon.io REST poller (when MASSIVE_API_KEY set)
        │  cache.update(ticker, price, ts, session_open)
        ▼
   PriceCache (thread-safe, in-memory, version counter)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

### Modules

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate` — frozen dataclass with tick-to-tick (`change`, `direction`) and daily (`session_open`, `day_change`, `day_change_percent`) fields; `normalize_ticker()` |
| `interface.py` | `MarketDataSource` — ABC: `start/stop/add_ticker/remove_ticker/get_tickers` |
| `cache.py` | `PriceCache` — thread-safe store; `snapshot()` for atomic (version, prices) reads; `remove()` bumps version |
| `seed_prices.py` | Seed prices, per-ticker GBM params, correlation constants, `UNKNOWN_SEED_RANGE` |
| `simulator.py` | `GBMSimulator` (Cholesky-correlated GBM, injectable RNG, shock events, Cholesky fallback) + `SimulatorDataSource` |
| `massive_client.py` | `parse_snapshot()` (pure) + `MassiveDataSource` (one call for all tickers, typed errors, exponential backoff, immediate poll on add) |
| `factory.py` | `create_market_data_source()` — `MASSIVE_API_KEY` selects source; `MASSIVE_POLL_INTERVAL` tunes polling |
| `stream.py` | `create_stream_router()` + `generate_price_events()` — SSE with version-based change detection and 15 s heartbeat |

### Key Design Decisions

- **Strategy pattern** — both sources implement the same ABC; downstream code reads only the cache
- **Two kinds of change** — `direction`/`change` vs. previous tick drive the flash; `day_change_percent` vs. `session_open` drives the watchlist "Chg %" column (simulator: seed price; Massive: `prev_day.close`)
- **Correct Massive SDK fields** — `last_trade.sip_timestamp` (ns), price fallback `last_trade → min → day → prev_day`. v1 read a non-existent `last_trade.timestamp` and failed against the live API; tests now use real `TickerSnapshot.from_dict` objects
- **Normalization everywhere** — both sources run `normalize_ticker()`, so `"aapl"` and `"AAPL"` are never two tickers
- **Fail soft** — bad ticks/snapshots/HTTP errors are logged and skipped; last prices stay in the cache

## Test Suite

**175 passed, 1 skipped** (live Massive smoke test; runs only with `MASSIVE_API_KEY`). 8 modules in `backend/tests/market/`.

| Module | Covers |
|--------|--------|
| test_models.py | `PriceUpdate` fields/serialization, daily change, `normalize_ticker` |
| test_cache.py | updates, version/remove semantics, `session_open` carry-forward, `snapshot()`, concurrent writers |
| test_simulator.py | GBM maths, determinism, empirical correlation & volatility, shocks, Cholesky fallback |
| test_simulator_source.py | lifecycle, normalization, `session_open`, loop resilience, no writes after stop |
| test_massive.py | `parse_snapshot` against real SDK models, polling, backoff, removal race, lifecycle |
| test_factory.py | source selection, `MASSIVE_POLL_INTERVAL` parsing |
| test_stream.py | SSE frames, change detection, heartbeat, removal, router re-entrancy, headers |
| test_interface.py | both sources conform to the ABC; public API exports |

Coverage: 99% (all modules 100% except one defensive line in `simulator.py`).

## Not yet built (app layer)

`get_tracked_tickers()` (watchlist ∪ open positions) and `sync_tracked_tickers(source)` belong to the DB/API layer and are specified in `MARKET_DATA_DESIGN.md` §12. They should be implemented alongside the watchlist and portfolio routes.

## Demo

```bash
cd backend
uv run market_data_demo.py
```

Live Rich terminal dashboard: all 10 tickers, sparklines, direction arrows, event log. Runs 60 s or until Ctrl+C.

## Usage for Downstream Code

```python
from app.market import PriceCache, create_market_data_source, create_stream_router, normalize_ticker

# Startup (FastAPI lifespan)
cache = PriceCache()
source = create_market_data_source(cache)       # reads MASSIVE_API_KEY
await source.start(["AAPL", "GOOGL", "MSFT"])   # cache populated before return
app.include_router(create_stream_router(cache)) # GET /api/stream/prices

# Read prices
update = cache.get("AAPL")             # PriceUpdate or None
price = cache.get_price("AAPL")        # float or None
update.day_change_percent              # daily change % (None if unknown)

# Dynamic watchlist
ticker = normalize_ticker(user_input)  # ValueError -> 422
await source.add_ticker(ticker)        # priced immediately
await source.remove_ticker("GOOGL")

# Shutdown
await source.stop()
```
