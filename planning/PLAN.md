# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenAI, with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |
| No login or auth | Personal learning project, single user on localhost. Do not build login, sessions, or API auth; all requests act as user `"default"`. If deployed publicly later, add simple protection then |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic (source code only, never the runtime database file). The backend initializes the database at startup — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume. The backend resolves it as `../db/finally.db` relative to `backend/`, which holds both locally and in the container (see §11).
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required for live chat (not needed when LLM_MOCK=true): OpenAI API key
OPENAI_API_KEY=your-openai-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses and never reads `OPENAI_API_KEY`; the app runs fully without a key
- If `LLM_MOCK` is not `true` → `OPENAI_API_KEY` is required for chat; the rest of the app works without it
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for all tracked tickers (see Tracked Tickers below) on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, and timestamp for each ticker
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### Tracked Tickers

- The market data source tracks the **union of watchlist tickers and tickers with an open position**
- Removing a ticker from the watchlist stops tracking it only if no position is held; a held ticker keeps streaming so P&L stays live and it can still be sold
- When a position is fully sold and the ticker is not on the watchlist, tracking stops
- At startup, the backend registers all watchlist and position tickers with the data source

### Ticker Validation

- A valid ticker is 1-5 letters, normalized to uppercase (regex `^[A-Z]{1,5}$` after uppercasing); anything else is rejected with 400
- Simulator mode accepts any valid symbol. Unknown symbols get a random seed price ($50-$300) and default GBM parameters (already implemented)
- Massive mode accepts any valid symbol; a symbol with no data simply has no price until the API returns one

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- The server checks the cache every ~500ms and sends an event only when the cache has changed (version counter)
- The first message is `retry: 1000` so the browser reconnects after 1 second
- Each event is a single `data:` line holding a JSON object of **all tracked tickers keyed by symbol**:

```
data: {"AAPL": {"ticker": "AAPL", "price": 190.5, "previous_price": 190.32, "timestamp": 1730000000.123, "change": 0.18, "change_percent": 0.0946, "direction": "up"}, "MSFT": {...}}
```

- `change` and `change_percent` are tick-to-tick (vs. `previous_price`), not daily; `direction` is `"up"`, `"down"`, or `"flat"`; `timestamp` is Unix epoch seconds
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Startup Initialization

The backend checks for the SQLite database at startup (in the FastAPI lifespan, before background tasks start). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

Every table except `users_profile` includes a `user_id` column defaulting to `"default"`; `users_profile` uses its `id` column (also `"default"`) as the user key. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution. No retention limit: at ~2,900 rows/day growth is negligible for a demo. `GET /api/portfolio/history` returns at most the latest 1,000 snapshots.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

### Response Shapes (the frontend/backend contract)

All numbers are JSON numbers (floats); all timestamps in REST responses are ISO 8601 UTC strings. Tickers are uppercase.

**Errors** — every non-2xx response uses FastAPI's default shape:

```json
{"detail": "Insufficient cash: need $1905.00, have $1200.00"}
```

| Status | When |
|---|---|
| 400 | Business rule failure: insufficient cash/shares, invalid ticker format, no price available yet, quantity <= 0, duplicate watchlist add |
| 404 | Watchlist DELETE for a ticker not on the watchlist |
| 422 | Request body fails schema validation (FastAPI default) |

**`GET /api/portfolio`**

```json
{
  "cash_balance": 8095.0,
  "total_value": 10012.4,
  "positions_value": 1917.4,
  "unrealized_pnl": 12.4,
  "positions": [
    {
      "ticker": "AAPL",
      "quantity": 10,
      "avg_cost": 190.5,
      "current_price": 191.74,
      "market_value": 1917.4,
      "unrealized_pnl": 12.4,
      "pnl_percent": 0.6509
    }
  ]
}
```

`total_value = cash_balance + positions_value`. `pnl_percent` is in percent units. If a held ticker has no cached price, `current_price` falls back to `avg_cost`.

**`POST /api/portfolio/trade`** — request `{"ticker": "AAPL", "quantity": 10, "side": "buy"}`; response 200:

```json
{
  "trade": {"id": "uuid", "ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.5, "executed_at": "2026-11-03T14:00:00Z"},
  "portfolio": { "...same shape as GET /api/portfolio..." }
}
```

**`GET /api/portfolio/history`**

```json
{"snapshots": [{"total_value": 10000.0, "recorded_at": "2026-11-03T14:00:00Z"}]}
```

Ordered oldest first.

**`GET /api/watchlist`**

```json
{"tickers": [{"ticker": "AAPL", "price": 190.5, "previous_price": 190.32, "direction": "up", "added_at": "2026-11-03T14:00:00Z"}]}
```

`price`, `previous_price`, and `direction` are `null` if no price is cached yet. Ordered by `added_at`.

**`POST /api/watchlist`** — request `{"ticker": "PYPL"}`; response 201 with the new entry (same item shape as above). **`DELETE /api/watchlist/{ticker}`** — response 204, no body.

**`POST /api/chat`** — request `{"message": "Buy 5 NVDA"}`; response 200:

```json
{
  "message": "Bought 5 NVDA at $875.20.",
  "actions": {
    "trades": [
      {"ticker": "NVDA", "side": "buy", "quantity": 5, "status": "executed", "price": 875.2, "error": null}
    ],
    "watchlist_changes": [
      {"ticker": "PYPL", "action": "add", "status": "failed", "error": "PYPL is already on the watchlist"}
    ]
  }
}
```

`status` is `"executed"` or `"failed"`; `error` is set only when failed. The `actions` object is what gets stored in `chat_messages.actions`. LLM call failures return 502 with `{"detail": "..."}`.

**`GET /api/health`** — `{"status": "ok"}`.

### Trade Rules

- `quantity` must be > 0; fractional quantities are allowed
- Fill price is the current cached price; if the ticker has no cached price, the trade is rejected (400)
- Buy: requires `cash_balance >= quantity * price`. New `avg_cost` = weighted average of old and new lots
- Sell: requires held quantity >= `quantity`. `avg_cost` is unchanged by sells
- A position whose quantity falls below `1e-9` after a sell is deleted (avoids float residue)
- Only tracked tickers have prices, so a buy of a ticker that is not tracked fails with "no price available" (400). Add it to the watchlist first; the LLM should add a watchlist entry before buying a new symbol
- Each trade writes a `trades` row and a `portfolio_snapshots` row in the same transaction

---

## 9. LLM Integration

When writing code to make calls to LLMs, use the `openai-llm` skill (`.claude/skills/openai-llm/SKILL.md`): LiteLLM calling OpenAI directly with the `openai/gpt-5-mini` model. Structured Outputs should be used to interpret the results.

For live chat, set `OPENAI_API_KEY` in the project root `.env` file and read it only in the backend. When `LLM_MOCK=true` the key is never read and may be absent.

Model constraints for `gpt-5-mini`: do not pass `temperature` or `top_p` (only defaults are supported); use `reasoning_effort="low"` for chat latency.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads the last 20 messages from the `chat_messages` table, oldest first
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenAI, requesting structured output
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (shape in §8 `POST /api/chat`); the frontend shows a loading indicator while waiting

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message`: The conversational text shown to the user
- `trades`: Array of trades to auto-execute (empty array if none). Each trade goes through the same validation as manual trades (§8 Trade Rules)
- `watchlist_changes`: Array of watchlist modifications, `action` is `"add"` or `"remove"` (empty array if none)

All three fields are **required** in the schema. OpenAI strict structured outputs require every property to be listed as required, so "no trades" is expressed as `[]`, not by omitting the field. Define the schema as Pydantic models and pass the model class as `response_format`.

Watchlist changes execute before trades, so "add PYPL and buy 5" works in one response.

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses without calling OpenAI and without reading `OPENAI_API_KEY`. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

The mock produces a structured response that then goes through the **same** execution path as a real one (validation, execution, storage). Rules, matched case-insensitively on the user message, first match wins:

| User message contains | Mock response |
|---|---|
| `buy` | message `"Mock: buying 1 AAPL."`, trades `[{"ticker": "AAPL", "side": "buy", "quantity": 1}]` |
| `sell` | message `"Mock: selling 1 AAPL."`, trades `[{"ticker": "AAPL", "side": "sell", "quantity": 1}]` |
| `watch` | message `"Mock: adding PYPL to your watchlist."`, watchlist_changes `[{"ticker": "PYPL", "action": "add"}]` |
| anything else | message `"Mock: I am FinAlly, your AI trading assistant."`, no actions |

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), session change % (vs. the first price received since page load; no daily open/close is available from the simulator), and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 24 slim (current LTS)
  - Copy frontend/
  - npm ci && npm run build (produces static export in frontend/out/)

Stage 2: Python 3.13 slim
  - Install uv
  - Copy backend/ to /app/backend/   (NOT /app — keeps backend/db/ schema files away from the /app/db volume)
  - WORKDIR /app/backend
  - uv sync --frozen (install Python dependencies from lockfile)
  - Copy frontend/out/ to /app/backend/static/
  - Expose port 8000
  - CMD: uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Container layout mirrors the repo: `/app/backend/` (code, including `backend/db/` schema) and `/app/db/` (volume, holds `finally.db`). The backend opens `../db/finally.db` relative to its working directory in both environments.

FastAPI serves the static frontend files and all API routes on port 8000. Register all `/api/*` routers first, then mount the static export last with `app.mount("/", StaticFiles(directory="static", html=True))` so it never shadows API routes. The app is a single page, so no client-side route fallback is needed.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `finally.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection
