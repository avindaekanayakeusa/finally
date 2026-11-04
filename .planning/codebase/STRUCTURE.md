---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# Codebase Structure

**Analysis Date:** 2026-11-04

## Directory Layout

```
finally/
├── backend/                  # FastAPI uv project (Python 3.12+; Docker uses 3.13)
│   ├── app/                  # Application package (imported as `app`)
│   │   ├── main.py           # FastAPI app, lifespan, snapshot loop, static mount
│   │   ├── db/               # SQLite connection, seeding, ticker reconciliation
│   │   ├── market/           # Price sources, cache, SSE stream
│   │   ├── portfolio/        # Trades, portfolio valuation, snapshots
│   │   ├── watchlist/        # Watchlist CRUD
│   │   └── chat/             # LLM chat, mock, schema, action execution
│   ├── db/schema.sql         # DDL + seed source (not runtime DB)
│   ├── tests/                # pytest suites mirroring app/ layout
│   ├── market_data_demo.py   # Standalone demo script (not imported by app)
│   ├── pyproject.toml        # uv/hatchling project definition
│   ├── uv.lock               # Locked Python dependencies
│   ├── README.md             # Backend readme (copied into Docker image)
│   └── CLAUDE.md             # Backend agent instructions
├── frontend/                 # Next.js 16 + React 19 + TypeScript (static export)
│   ├── app/                  # App Router: layout, page, global CSS, favicon
│   ├── components/           # UI components (Terminal, Watchlist, ChatPanel, ...)
│   ├── hooks/                # usePriceStream, useTerminal
│   ├── lib/                  # API client, types, formatting, portfolio math, treemap
│   ├── public/               # Static assets
│   ├── test/setup.ts         # Vitest setup
│   ├── out/                  # Build output (generated, gitignored)
│   ├── next.config.ts        # Static export + dev /api rewrite
│   ├── vitest.config.mts     # Unit test config
│   ├── package.json          # npm manifest
│   └── AGENTS.md             # Agent notes for this Next.js version
├── planning/                 # Project-wide agent docs (PLAN.md is the spec)
│   ├── PLAN.md               # Full project specification
│   ├── MARKET_DATA_SUMMARY.md
│   ├── MARKET_DATA_DESIGN.md
│   ├── REVIEW.md
│   ├── TEAM.md
│   └── archive/              # Historical market data design docs
├── test/                     # Playwright E2E tests
│   ├── tests/                # 01-fresh-start, 02-api, 03-ui specs; helpers.ts
│   ├── docker-compose.test.yml
│   ├── playwright.config.ts
│   └── package.json
├── scripts/                  # start/stop wrappers for Docker (mac and Windows)
├── db/                       # Runtime volume mount point; finally.db created here (gitignored)
│   └── .gitkeep
├── .github/workflows/        # CI and Claude workflow definitions
├── .planning/codebase/       # GSD codebase maps (this document lives here)
├── Dockerfile                # Multi-stage: Node 24 build -> Python 3.13 runtime
├── docker-compose.yml        # Single service `finally`, volume `finally-data`
├── .env / .env.example       # Environment config (.env is secret, never commit)
├── CLAUDE.md                 # Root project instructions for agents
├── README.md
└── LICENSE
```

Notes on the tree:
- `Independent reviewer/` at the repo root holds a Claude plugin (`.claude-plugin/`). It is not part of the app.
- `backend/.pytest_cache/` and `backend/.ruff_cache/` are tooling caches.
- `frontend/out/` is a build artifact and is copied into `backend/static/` in the Docker build. Note that `backend/static/` does not exist in the repo; `main.py` mounts it only if present.

## Directory Purposes

**`backend/app/`:**
- Purpose: All server code.
- Contains: Python packages, one per domain (`db`, `market`, `portfolio`, `watchlist`, `chat`), plus `main.py`.
- Key files: `backend/app/main.py`, `backend/app/db/connection.py`, `backend/app/market/interface.py`, `backend/app/portfolio/service.py`, `backend/app/chat/llm.py`.

**`backend/app/db/`:**
- Purpose: Database access and bootstrap.
- Contains: `connection.py` (paths, `get_connection`, `get_db`, `init_db`, `_seed`), `tickers.py` (validation and tracked-ticker sync), `__init__.py` (public exports).
- Key files: `backend/app/db/connection.py`.

**`backend/app/market/`:**
- Purpose: Market data producers, shared cache, and SSE endpoint.
- Contains: `interface.py`, `simulator.py`, `massive_client.py`, `factory.py`, `cache.py`, `models.py`, `seed_prices.py`, `stream.py`, `__init__.py`.
- Key files: `backend/app/market/interface.py`, `backend/app/market/factory.py`, `backend/app/market/cache.py`.

**`backend/app/portfolio/`:**
- Purpose: Cash, positions, trades, valuation, snapshots.
- Contains: `routes.py` (`/api/portfolio`), `service.py`, `__init__.py`.
- Key files: `backend/app/portfolio/service.py`.

**`backend/app/watchlist/`:**
- Purpose: Watchlist list/add/remove.
- Contains: `routes.py` (`/api/watchlist`), `service.py`, `__init__.py`.

**`backend/app/chat/`:**
- Purpose: Chat endpoint and LLM orchestration.
- Contains: `router.py`, `llm.py`, `mock.py`, `schema.py`, `context.py`, `history.py`, `execute.py`, `__init__.py`.

**`backend/db/`:**
- Purpose: Schema SQL source. Lives outside `app/` on purpose so the runtime DB path `/app/db` does not collide with it in the container.
- Contains: `schema.sql` only.

**`backend/tests/`:**
- Purpose: pytest suites. Layout mirrors `app/`.
- Contains: `api/`, `chat/`, `db/`, `market/`, `portfolio/`, `watchlist/`, plus `conftest.py` at root and in `chat/`.
- Run: `uv run pytest` from `backend/`.

**`frontend/app/`:**
- Purpose: Next.js App Router shell.
- Contains: `layout.tsx`, `page.tsx`, `globals.css`, `favicon.ico`.

**`frontend/components/`:**
- Purpose: All visual components, flat (no subfolders).
- Contains: `Terminal.tsx` (root layout), `Header.tsx`, `Watchlist.tsx`, `WatchlistRow.tsx`, `Sparkline.tsx`, `LineChart.tsx`, `Heatmap.tsx`, `PositionsTable.tsx`, `TradeBar.tsx`, `ChatPanel.tsx`, `PanelTitle.tsx`, `components.test.tsx`.

**`frontend/hooks/`:**
- Purpose: Stateful data hooks.
- Contains: `usePriceStream.ts` (SSE), `useTerminal.ts` (REST state and actions).

**`frontend/lib/`:**
- Purpose: Framework-free helpers and types.
- Contains: `api.ts` (fetch wrapper for `/api/*`), `types.ts`, `format.ts`, `portfolio.ts`, `treemap.ts`, `lib.test.ts`.

**`test/`:**
- Purpose: End-to-end tests run against the container with `LLM_MOCK=true`.
- Contains: Playwright specs in `test/tests/`, `docker-compose.test.yml`, `playwright.config.ts`.

**`planning/`:**
- Purpose: Shared agent reference docs. `PLAN.md` is the contract. Historical docs live in `planning/archive/`.

**`scripts/`:**
- Purpose: Start and stop the Docker container.
- Contains: `start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1`.

**`db/`:**
- Purpose: Runtime volume target. The backend writes `db/finally.db` here (path resolved as `<repo>/db/finally.db` in local dev, `/app/db/finally.db` in the container).
- Generated: Yes (at runtime). Committed: only `.gitkeep`.

**`.github/workflows/`:**
- Purpose: GitHub Actions: `blank.yml`, `claude.yml`, `claude-code-review.yml`.

## Key File Locations

**Entry Points:**
- `backend/app/main.py`: FastAPI app and lifespan.
- `frontend/app/page.tsx`: Single page; renders `Terminal`.
- `Dockerfile`: Container build and CMD.

**Configuration:**
- `backend/pyproject.toml`: Python deps and build backend.
- `frontend/package.json`: npm deps and scripts.
- `frontend/next.config.ts`: `output: "export"` for production, `/api` rewrite for dev.
- `frontend/tsconfig.json`: TypeScript config and `@/` alias.
- `frontend/vitest.config.mts`: Unit test runner config.
- `.env.example`: Template for environment variables.
- `docker-compose.yml`: Optional single-service compose file.

**Core Logic:**
- `backend/app/portfolio/service.py`: Trade execution and valuation.
- `backend/app/chat/execute.py`: LLM action execution.
- `backend/app/market/simulator.py`: GBM simulator.
- `backend/app/market/stream.py`: SSE generator.
- `frontend/hooks/useTerminal.ts`: Client state and actions.
- `frontend/hooks/usePriceStream.ts`: Live price state.

**Testing:**
- `backend/tests/`: pytest unit and API tests.
- `frontend/components/components.test.tsx`, `frontend/lib/lib.test.ts`: Vitest tests.
- `test/tests/`: Playwright E2E.

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (`massive_client.py`, `history.py`).
- Python package folders: lowercase single words (`market`, `portfolio`).
- React components: `PascalCase.tsx` (`Terminal.tsx`, `WatchlistRow.tsx`).
- React hooks: `useCamelCase.ts` (`usePriceStream.ts`).
- Library modules: lowercase `camelCase` or single word (`api.ts`, `treemap.ts`).
- Tests: Python `test_<module>.py` under `tests/<domain>/`; TypeScript `*.test.ts(x)` co-located in `frontend/components/` and `frontend/lib/`; Playwright `NN-name.spec.ts` in `test/tests/`.
- Planning docs: `UPPERCASE.md`.

**Directories:**
- Backend: lowercase, one per domain under `backend/app/`.
- Frontend: lowercase plural folders (`components`, `hooks`, `lib`).

**Code:**
- Python functions and variables: `snake_case`; classes `PascalCase`; constants `UPPER_SNAKE` (`DEFAULT_USER`, `SNAPSHOT_INTERVAL`).
- Router factories: `create_<domain>_router`.
- Service errors: `<Domain>Error` (`TradeError`, `WatchlistError`).
- TypeScript: components and types `PascalCase`; functions `camelCase`.

## Where to Add New Code

**New REST feature in an existing domain (e.g., a new portfolio endpoint):**
- Service logic: `backend/app/portfolio/service.py`
- Route: `backend/app/portfolio/routes.py` (inside `create_portfolio_router`)
- Tests: `backend/tests/portfolio/test_service.py` and `backend/tests/api/test_routes.py`

**New domain module (backend):**
- Implementation: `backend/app/<domain>/` with `__init__.py`, `routes.py` (factory `create_<domain>_router(cache, source)`), `service.py`.
- Register in `backend/app/main.py` above the static mount.
- Tests: `backend/tests/<domain>/`.

**New market data provider:**
- Implementation: `backend/app/market/<name>_client.py` subclassing `MarketDataSource` from `backend/app/market/interface.py`.
- Wire into `backend/app/market/factory.py`.
- Tests: `backend/tests/market/test_<name>.py`, plus conformance checks in `backend/tests/market/test_interface.py`.

**New database table or column:**
- DDL: `backend/db/schema.sql` (include `user_id TEXT DEFAULT 'default'` for user-scoped tables).
- Access: via `get_connection()` in `backend/app/db/connection.py` and the owning service.

**New LLM-driven action:**
- Schema: `backend/app/chat/schema.py`
- Execution: `backend/app/chat/execute.py`
- Mock rule: `backend/app/chat/mock.py`

**New frontend component:**
- Implementation: `frontend/components/<PascalName>.tsx`; mount from `frontend/components/Terminal.tsx`.
- Data: pass props from `useTerminal` / `usePriceStream`; add REST calls to `frontend/lib/api.ts` and types to `frontend/lib/types.ts`.
- Tests: co-locate in `frontend/components/components.test.tsx` or add to `frontend/lib/lib.test.ts`.

**Pure frontend helper:**
- `frontend/lib/` (e.g., formatting in `frontend/lib/format.ts`, portfolio math in `frontend/lib/portfolio.ts`).

**New E2E scenario:**
- `test/tests/NN-<name>.spec.ts` with helpers in `test/tests/helpers.ts`.

**Shared utilities:**
- Backend ticker/symbol helpers: `backend/app/market/models.py` (`normalize_ticker`) and `backend/app/db/tickers.py` (`validate_ticker`).
- Frontend: `frontend/lib/format.ts`.

## Special Directories

**`db/`:**
- Purpose: Runtime SQLite file location.
- Generated: Yes (`finally.db` at runtime).
- Committed: Only `.gitkeep`; `finally.db` is gitignored.

**`frontend/out/`:**
- Purpose: Next.js static export.
- Generated: Yes (`npm run build`).
- Committed: No (build artifact). Copied to `backend/static/` in the Docker image.

**`backend/static/`:**
- Purpose: Where FastAPI serves the built frontend from.
- Generated: Yes (Docker build copies `frontend/out` here; not present in the repo).
- Committed: No.

**`backend/.pytest_cache/`, `backend/.ruff_cache/`, `backend/app/**/__pycache__/`:**
- Purpose: Tool caches.
- Generated: Yes. Committed: No.

**`frontend/node_modules/`, `backend/.venv/`:**
- Purpose: Dependency installs.
- Generated: Yes. Committed: No.

**`.planning/codebase/`:**
- Purpose: GSD-generated codebase maps consumed by planning commands.
- Generated: Yes. Committed: Per project policy.

---

*Structure analysis: 2026-11-04*
