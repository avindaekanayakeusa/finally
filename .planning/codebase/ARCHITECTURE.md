---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
<!-- refreshed: 2026-11-04 -->
# Architecture

**Analysis Date:** 2026-11-04

## System Overview

```text
┌──────────────────────────────────────────────────────────────────┐
│                 Browser (Next.js static export)                   │
│  `frontend/app/page.tsx` -> `components/Terminal.tsx`             │
│  hooks: `usePriceStream.ts` (EventSource), `useTerminal.ts` (REST)│
│  REST client: `frontend/lib/api.ts`                               │
└───────────────┬───────────────────────────────┬──────────────────┘
                │ GET /api/stream/prices (SSE)  │ /api/* (JSON)
                ▼                               ▼
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI app `backend/app/main.py` (port 8000)                    │
│  routers: `market/stream.py`, `portfolio/routes.py`,              │
│           `watchlist/routes.py`, `chat/router.py`                 │
│  static: StaticFiles mounted at "/" from `backend/static/`        │
├──────────────────────────────────────────────────────────────────┤
│  Services: `portfolio/service.py`, `watchlist/service.py`,        │
│            `chat/execute.py`, `chat/context.py`, `chat/llm.py`    │
├───────────────────────┬──────────────────────┬───────────────────┤
│  `db/` (sqlite3)      │  `market/` cache      │  LiteLLM -> OpenAI│
│  `db/finally.db`      │  `market/cache.py`    │  or `chat/mock.py`│
└───────────────────────┴──────────┬───────────┴───────────────────┘
                                   │ writes prices
                  ┌────────────────┴────────────────┐
                  │ MarketDataSource (ABC)           │
                  │ `market/simulator.py` (default)  │
                  │ `market/massive_client.py`       │
                  │ selected by `market/factory.py`  │
                  └──────────────────────────────────┘
```

## Pattern Overview

**Overall:** Modular monolith. One FastAPI process serves the REST API, the SSE stream, background tasks, and the pre-built Next.js frontend. The frontend is a client-only SPA built with `output: "export"` (`frontend/next.config.ts`), so there is no Node server at runtime.

**Key Characteristics:**
- Single process, single port (8000), single origin. No CORS configuration is needed; the frontend uses relative `/api/*` URLs.
- Shared in-memory price cache is the only channel between the market data producer and every consumer (SSE stream, portfolio valuation, watchlist, trades, chat context). Nothing downstream calls a market source for prices.
- Pluggable market data behind one ABC (`MarketDataSource` in `backend/app/market/interface.py`). The simulator and the Massive poller are interchangeable; selection is by the `MASSIVE_API_KEY` env var in `backend/app/market/factory.py`.
- Persistence is synchronous `sqlite3` with a fresh connection per request/operation (`backend/app/db/connection.py`). Service functions take an explicit `conn` argument.
- Single hardcoded user `"default"` (`DEFAULT_USER` in `backend/app/db/connection.py`). Every user-scoped table has a `user_id` column so multi-user support needs no schema change.
- Backend is a self-contained uv project (`backend/pyproject.toml`); frontend is a self-contained npm project (`frontend/package.json`). They communicate only over HTTP.

## Layers

**Market data (producer):**
- Purpose: Produce `PriceUpdate` records and write them into the shared cache.
- Location: `backend/app/market/`
- Contains: `interface.py` (ABC), `simulator.py` (GBM simulator), `massive_client.py` (REST poller), `factory.py`, `cache.py`, `models.py`, `seed_prices.py`, `stream.py` (SSE router).
- Depends on: `models.py`, `cache.py`.
- Used by: `backend/app/main.py` (lifespan start/stop), `backend/app/db/tickers.py` (add/remove tracked tickers), `backend/app/watchlist/service.py`, `backend/app/portfolio/routes.py` (via source reference).

**Price cache (shared state):**
- Purpose: Latest `PriceUpdate` per ticker plus a monotonically increasing version counter. Thread-safe.
- Location: `backend/app/market/cache.py`
- Contains: `PriceCache` class (`snapshot()` returns `(version, prices)`).
- Depends on: `backend/app/market/models.py`.
- Used by: the SSE generator in `backend/app/market/stream.py`, `backend/app/portfolio/service.py` (valuation and trade fill price), `backend/app/watchlist/service.py`, `backend/app/chat/context.py`.

**Persistence:**
- Purpose: Schema creation, seed data, connection management, ticker reconciliation.
- Location: `backend/app/db/` (code) and `backend/db/schema.sql` (DDL, source only).
- Contains: `connection.py` (`get_connection`, `get_db` FastAPI dependency, `init_db`, `_seed`), `tickers.py` (`validate_ticker`, `get_tracked_tickers`, `sync_tracked_tickers`).
- Depends on: `backend/app/market` (for the `MarketDataSource` type in `tickers.py`).
- Used by: every router and service.

**Domain services (business logic):**
- Purpose: Trade execution and portfolio math, watchlist management, chat context and action execution.
- Location: `backend/app/portfolio/service.py`, `backend/app/watchlist/service.py`, `backend/app/chat/execute.py`, `backend/app/chat/context.py`, `backend/app/chat/history.py`.
- Depends on: `db`, `market` (cache and source).
- Used by: routers and the chat executor.

**HTTP routers (transport):**
- Purpose: Map HTTP paths to services, define status codes and response shapes.
- Location: `backend/app/portfolio/routes.py`, `backend/app/watchlist/routes.py`, `backend/app/chat/router.py`, `backend/app/market/stream.py`, `/api/health` defined inline in `backend/app/main.py`.
- Pattern: each module exposes a factory `create_<name>_router(cache, source) -> APIRouter`. Routers are built per call, so no duplicate routes are registered.

**LLM integration:**
- Purpose: Turn a chat message plus portfolio context into a structured `LLMResponse`.
- Location: `backend/app/chat/llm.py` (LiteLLM call with Pydantic `response_format`), `backend/app/chat/mock.py` (deterministic responses when `LLM_MOCK=true`), `backend/app/chat/schema.py` (Pydantic models), `backend/app/chat/context.py` (system prompt input).
- Depends on: `schema.py`, environment variables.
- Used by: `backend/app/chat/router.py`.

**Frontend presentation:**
- Purpose: Terminal UI, live price rendering, charts, trade and chat forms.
- Location: `frontend/app/` (Next.js App Router shell), `frontend/components/`, `frontend/hooks/`, `frontend/lib/`.
- Depends on: `/api/*` and `/api/stream/prices` only.
- Used by: the browser.

## Data Flow

### Live Price Path (SSE)

1. Source task writes `PriceUpdate` objects into the cache, bumping the version (`backend/app/market/simulator.py` or `backend/app/market/massive_client.py` -> `backend/app/market/cache.py`).
2. `generate_price_events` in `backend/app/market/stream.py` polls `price_cache.snapshot()` every 0.5 s and emits a `data:` frame with all tracked tickers only when the version changes; emits `: ping` after 15 s idle.
3. `frontend/hooks/usePriceStream.ts` opens `new EventSource("/api/stream/prices")`, keeps the latest map and per-ticker history, and derives connection status from `readyState`.
4. `frontend/components/Terminal.tsx` passes the stream into the watchlist, header, and trade bar. Price flashes are CSS-driven (`useFlash` in `frontend/components/WatchlistRow.tsx`).

### Trade Path

1. User submits the trade bar (`frontend/components/TradeBar.tsx`) -> `useTerminal.ts` calls `api.trade` (`frontend/lib/api.ts`).
2. `POST /api/portfolio/trade` (`backend/app/portfolio/routes.py`) calls `execute_trade` in `backend/app/portfolio/service.py`.
3. Fill price is read from the cache; missing price raises `TradeError` -> HTTP 400.
4. Buy/sell updates `users_profile`, `positions`, inserts `trades`, and inserts a `portfolio_snapshots` row in one transaction.
5. Frontend refreshes portfolio and history (`useTerminal.ts`).

### Chat Path

1. `POST /api/chat` (`backend/app/chat/router.py`) builds context from DB and cache (`chat/context.py`), loads the last 20 messages (`chat/history.py`), and assembles messages with `build_messages`.
2. `get_llm_response` (`chat/llm.py`) calls LiteLLM -> `openai/gpt-5-mini`, or `chat/mock.py` when `LLM_MOCK=true`. Failures return HTTP 502.
3. `execute_actions` (`chat/execute.py`) applies watchlist changes first, then trades via the same `execute_trade` used by the REST route, then calls `sync_tracked_tickers` if any trade ran.
4. The user and assistant messages (with `actions` JSON) are saved to `chat_messages`; the response is returned as one JSON body (no streaming).

### Snapshot Path

1. `snapshot_loop` in `backend/app/main.py` runs every 30 s and calls `record_snapshot` (`backend/app/portfolio/service.py`) with a fresh connection.
2. Frontend reads `GET /api/portfolio/history` on load and every `HISTORY_REFRESH_MS` (`frontend/hooks/useTerminal.ts`).

**State Management:**
- Server: source of truth is SQLite (cash, positions, watchlist, trades, snapshots, chat) plus the in-memory `PriceCache` (prices only, lost on restart).
- Client: React state in hooks. `usePriceStream` holds live prices and sparkline history accumulated since page load; `useTerminal` holds portfolio, watchlist, snapshots, and chat messages fetched from REST.

## Key Abstractions

**MarketDataSource:**
- Purpose: Uniform lifecycle for any price provider.
- Definition: `backend/app/market/interface.py` (`start`, `stop`, `add_ticker`, `remove_ticker`, `get_tickers`).
- Implementations: `backend/app/market/simulator.py` (`SimulatorDataSource`), `backend/app/market/massive_client.py` (`MassiveDataSource`).
- Pattern: strategy; chosen once at import time in `backend/app/main.py` via `create_market_data_source`.

**PriceCache / PriceUpdate:**
- Purpose: Decouple producers from consumers; single source of latest prices.
- Examples: `backend/app/market/cache.py`, `backend/app/market/models.py`.
- Pattern: shared mutable object with a lock and version counter; `normalize_ticker` in `models.py` is the canonical ticker normalizer.

**Service functions over a connection:**
- Purpose: Pure-ish business operations taking `(conn, cache, ...)`.
- Examples: `execute_trade`, `get_portfolio`, `record_snapshot` in `backend/app/portfolio/service.py`; `add_ticker`, `remove_ticker`, `list_watchlist` in `backend/app/watchlist/service.py`.
- Pattern: transaction via `with conn:` inside the service; routers translate `TradeError`/`WatchlistError` into HTTP errors.

**Router factories:**
- Purpose: Inject shared cache and source into routers without globals in route modules.
- Examples: `create_stream_router`, `create_portfolio_router`, `create_watchlist_router`, `create_chat_router`.
- Pattern: `create_*_router(cache, source) -> APIRouter`, registered in `backend/app/main.py`.

**Pydantic LLM schema:**
- Purpose: Structured outputs from OpenAI; same model validates mock output.
- Examples: `backend/app/chat/schema.py` (`LLMResponse`, `TradeInstruction`, `WatchlistInstruction`).
- Pattern: all fields required (OpenAI strict mode); "none" is `[]`.

## Entry Points

**Backend application:**
- Location: `backend/app/main.py` (`app = FastAPI(title="FinAlly", lifespan=lifespan)`).
- Triggers: `uvicorn app.main:app` (Docker `CMD` in `Dockerfile`; local dev per `backend/README.md`).
- Responsibilities: load `.env` from project root, init DB, start market source with tracked tickers, start snapshot task, register routers, mount static files last.

**Frontend page:**
- Location: `frontend/app/page.tsx` (renders `Terminal`); layout in `frontend/app/layout.tsx`.
- Triggers: browser request to `/` (served from `backend/static/` in production; `next dev` on port 3000 with `/api` rewrites in `frontend/next.config.ts` in development).
- Responsibilities: mount the terminal UI.

**Container:**
- Location: `Dockerfile` (stage 1 Node 24 builds `frontend/out`; stage 2 Python 3.13 runs uvicorn), `docker-compose.yml`.
- Triggers: `scripts/start_mac.sh`, `scripts/start_windows.ps1`.

**Market demo script:**
- Location: `backend/market_data_demo.py` (standalone, not imported by the app).

## Architectural Constraints

- **Threading:** Single asyncio event loop in uvicorn. Market simulator and Massive poller run as asyncio tasks. `PriceCache` uses a `threading.Lock` so it is safe if accessed from threads. SQLite connections are created with `check_same_thread=False`; routes using sync `def` run in FastAPI's threadpool.
- **Global state:** Module-level singletons in `backend/app/main.py`: `price_cache` and `market_source` (created at import time). `DEFAULT_USER` constant in `backend/app/db/connection.py`.
- **Startup ordering:** `load_dotenv` and the market source factory run at module import, before `lifespan`. `init_db()` must run before `get_tracked_tickers` (done in lifespan).
- **Circular imports:** `backend/app/db/tickers.py` imports `app.market`; `backend/app/chat/execute.py` imports `app.portfolio.service` and `app.watchlist.service`, which both import `app.db`. Keep `app.db` free of imports from services.
- **Static mount order:** `StaticFiles` must remain the last `include`/`mount` in `backend/app/main.py` or it shadows `/api/*`. Static mount is skipped if `backend/static/` does not exist (dev mode).
- **Database path:** `FINALLY_DB_PATH` overrides; default is `<repo>/db/finally.db` (`backend/app/db/connection.py`).
- **Snapshot task scope:** the loop records only the default user.

## Anti-Patterns

### Reading prices directly from the source

**What happens:** Code calls `market_source` or a provider API to get a price.
**Why it's wrong:** Bypasses the cache, so the value can differ from what the SSE stream shows and breaks the single-producer design.
**Do this instead:** Read from `PriceCache` (`cache.get`/`snapshot` in `backend/app/market/cache.py`), as `backend/app/portfolio/service.py` does.

### Building a trade outside `execute_trade`

**What happens:** Writing to `positions` or `users_profile` directly from a route or the chat executor.
**Why it's wrong:** Skips validation, the `trades` row, and the `portfolio_snapshots` row that must share one transaction.
**Do this instead:** Call `execute_trade` in `backend/app/portfolio/service.py`; the chat path already does this in `backend/app/chat/execute.py`.

### Adding a route to the module-level app after the static mount

**What happens:** `app.include_router(...)` placed after `app.mount("/", ...)` in `backend/app/main.py`.
**Why it's wrong:** Static files at `/` can capture the request.
**Do this instead:** Register all `/api` routers above the mount.

### Creating a second frontend data source

**What happens:** Components open their own `EventSource` or fetch the same endpoints independently.
**Why it's wrong:** Duplicate SSE connections and divergent state.
**Do this instead:** Use the existing `usePriceStream` (`frontend/hooks/usePriceStream.ts`) and `useTerminal` (`frontend/hooks/useTerminal.ts`) and pass data down as props.

## Error Handling

**Strategy:** Domain errors are raised as typed exceptions in services and converted to HTTP status codes in routers.

**Patterns:**
- `TradeError` (`backend/app/portfolio/service.py`) and `WatchlistError` / `WatchlistNotFound` (`backend/app/watchlist/service.py`) map to 400/404 in their routes.
- `ValueError` from `validate_ticker` (`backend/app/db/tickers.py`) maps to 400.
- LLM call exceptions become HTTP 502 in `backend/app/chat/router.py`.
- Background snapshot failures are logged with `logger.exception` and do not stop the loop (`backend/app/main.py`).
- Chat action failures are recorded per item in the `actions` object with `status: "failed"` and `error` (`backend/app/chat/execute.py`) so the LLM can report them.
- Frontend `EventSource` reconnects automatically; `retry: 1000` is sent by the server.

## Cross-Cutting Concerns

**Logging:** Standard `logging` with `basicConfig` in `backend/app/main.py`; module loggers via `logging.getLogger(__name__)`.
**Validation:** Pydantic request models in `backend/app/chat/schema.py` and route bodies; ticker regex in `backend/app/db/tickers.py`; numeric checks in `backend/app/portfolio/service.py`.
**Authentication:** None by design. All requests act as `"default"`.
**Configuration:** Environment variables read in `backend/app/main.py`, `backend/app/market/factory.py`, `backend/app/chat/llm.py`, `backend/app/db/connection.py`. Root `.env` is loaded for local dev; Docker uses `--env-file` / `env_file: .env`.

---

*Architecture analysis: 2026-11-04*
