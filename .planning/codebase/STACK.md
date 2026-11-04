---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# Technology Stack

**Analysis Date:** 2026-11-04

## Languages

**Primary:**
- Python 3.13 (Docker runtime, `python:3.13-slim`); `requires-python = ">=3.12"` in `backend/pyproject.toml` - all backend code under `backend/app/`
- TypeScript 5 (`typescript ^5` in `frontend/package.json`) - all frontend code under `frontend/app/`, `frontend/components/`, `frontend/hooks/`, `frontend/lib/`

**Secondary:**
- SQL (SQLite dialect) - schema in `backend/db/schema.sql`
- Bash and PowerShell - start/stop scripts in `scripts/` (`start_mac.sh`, `stop_mac.sh`, `start_windows.ps1`, `stop_windows.ps1`)
- CSS (Tailwind v4 via `@import "tailwindcss"`) - `frontend/app/globals.css`
- TypeScript (Playwright E2E) - `test/tests/`, `test/playwright.config.ts`

## Runtime

**Backend:**
- CPython 3.13 in the container (`Dockerfile`, stage 2 `FROM python:3.13-slim`)
- Local dev venv at `backend/.venv` (not committed)
- Package manager: `uv` (image pinned to `ghcr.io/astral-sh/uv:0.13.6`, copied into the Dockerfile)
- Lockfile: present - `backend/uv.lock`
- Install in image: `uv sync --frozen`; run: `uv run --no-sync uvicorn app.main:app`

**Frontend:**
- Node.js 24 (`node:24-slim` build stage in `Dockerfile`; `@types/node ^24`)
- Package manager: npm
- Lockfile: present - `frontend/package-lock.json` (also `test/package-lock.json`)

**E2E test runner:**
- Node packages in `test/` with Playwright image `mcr.microsoft.com/playwright:v1.64.1-noble` (`test/docker-compose.test.yml`)

## Frameworks

**Backend core:**
- FastAPI `0.128.7` (locked; `fastapi>=0.115.0`) - HTTP API, routers, lifespan, static file mount (`backend/app/main.py`)
- Uvicorn `0.40.0` (locked; `uvicorn[standard]>=0.32.0`) - ASGI server, started by the Dockerfile `CMD`
- Pydantic `2.12.5` (locked, transitive via FastAPI) - request/response models and the LLM structured-output schema (`backend/app/chat/schema.py`)
- Python stdlib `sqlite3` - persistence (`backend/app/db/connection.py`); no ORM

**Frontend core:**
- Next.js `16.4.5` (`frontend/package.json`) - built as a static export (`output: "export"`, `images: { unoptimized: true }`) in `frontend/next.config.ts`; `next dev` rewrites `/api/*` to `BACKEND_URL` (default `http://localhost:8000`)
- React `19.3.0` and react-dom `19.3.0` - UI
- Tailwind CSS `^4` with `@tailwindcss/turbopack` - styling; theme tokens defined in `frontend/app/globals.css` (`@theme`)
- lightweight-charts `5.2.1` - canvas charting for the price/P&L charts (imported from `lightweight-charts`)

**Testing:**
- pytest `>=8.3.0`, pytest-asyncio `>=0.24.0` (`asyncio_mode = "auto"`), pytest-cov `>=5.0.0` - backend unit tests in `backend/tests/` (config in `backend/pyproject.toml`)
- Vitest `5.1.0` with jsdom and `@vitejs/plugin-react ^6.2.1` - frontend unit tests (`frontend/vitest.config.mts`, setup at `frontend/test/setup.ts`, tests `**/*.test.{ts,tsx}`)
- React Testing Library `^16.3.3`, `@testing-library/dom ^10.4.2`, `@testing-library/jest-dom ^7.0.1`, `@testing-library/user-event ^14.6.8` - frontend component tests
- Playwright `1.64.1` (`@playwright/test`) - E2E in `test/tests/`, config `test/playwright.config.ts`, runs serially (`workers: 1`) against `BASE_URL`

**Build/Dev:**
- hatchling - Python build backend (`backend/pyproject.toml` `[build-system]`, wheel packages `app`)
- ruff `>=0.7.0` - lint/format for backend (`[tool.ruff]`: line-length 100, target py312, rules E, F, I, N, W)
- TypeScript compiler, `frontend/tsconfig.json` (`strict: true`, `moduleResolution: bundler`, alias `@/*` -> `frontend/*`)
- `@vitejs/plugin-react` for Vitest transforms

## Key Dependencies

**Backend (runtime, `backend/pyproject.toml`):**
- `litellm` `1.108.0` (locked; `>=1.108.0`) - LLM client; `acompletion` call to `openai/gpt-5-mini` in `backend/app/chat/llm.py`
- `massive` `2.2.0` (locked; `>=1.0.0`) - Massive (formerly Polygon.io) REST client, `RESTClient` in `backend/app/market/massive_client.py`
- `numpy` `2.4.2` (locked; `>=2.0.0`) - GBM simulator random generator (`np.random.default_rng`) in `backend/app/market/simulator.py`
- `python-dotenv` `>=1.2.4` - loads `<repo>/.env` for local runs in `backend/app/main.py`
- `rich` `>=13.0.0` - declared dependency; used by `backend/market_data_demo.py` (not by the app server)

**Frontend (runtime, `frontend/package.json`):**
- `next`, `react`, `react-dom`, `lightweight-charts` (see Frameworks)

**Infrastructure:**
- SQLite file database at `db/finally.db` (repo root; `DEFAULT_DB_PATH` in `backend/app/db/connection.py`), overridable by `FINALLY_DB_PATH`
- Docker image `finally` built from `Dockerfile`; volume `finally-data` mounted at `/app/db`

## Configuration

**Environment variables (names from `.env.example`, plus code-read names):**
- `OPENAI_API_KEY` - required for live chat when `LLM_MOCK` is not `true`; read only through LiteLLM (`backend/app/chat/llm.py`)
- `MASSIVE_API_KEY` - optional; when non-empty, selects `MassiveDataSource`; otherwise the simulator (`backend/app/market/factory.py`)
- `MASSIVE_POLL_INTERVAL` - optional seconds between Massive polls, default 15, minimum 1 (`backend/app/market/factory.py`; commented out in `.env.example`)
- `LLM_MOCK` - `true` (case-insensitive) returns deterministic mock responses and skips the LLM (`backend/app/chat/llm.py`)
- `FINALLY_DB_PATH` - optional SQLite path override (`backend/app/db/connection.py`)
- `BACKEND_URL` - frontend dev-server proxy target only (`frontend/next.config.ts`), default `http://localhost:8000`

**Env file:**
- `.env` exists at repo root (gitignored; loaded by `backend/app/main.py` and passed to Docker via `--env-file` in `scripts/start_mac.sh` and `scripts/start_windows.ps1`; `docker-compose.yml` uses `env_file: .env`). Its contents are not recorded here.
- `.env.example` is committed at repo root and lists `OPENAI_API_KEY`, `MASSIVE_API_KEY`, `LLM_MOCK`, with `MASSIVE_POLL_INTERVAL` commented out.
- Test override: `test/docker-compose.test.yml` sets `LLM_MOCK: "true"` and `MASSIVE_API_KEY: ""`.

**Build:**
- `frontend/next.config.ts` - static export config
- `frontend/tsconfig.json`, `frontend/vitest.config.mts`, `frontend/postcss` not present (Tailwind via Turbopack plugin)
- `backend/pyproject.toml` - dependencies, ruff, pytest, coverage config
- `Dockerfile` - multi-stage: `node:24-slim` builds `frontend/out`, then `python:3.13-slim` serves it from `/app/backend/static`
- `.dockerignore` - excludes `.git`, `.claude`, `.env`, `db`, `test`, `planning`, `**/.venv`, `**/node_modules`, `frontend/.next`, `frontend/out`, `backend/static`
- `.github/workflows/` - `blank.yml` (placeholder CI echo job, runs on push/PR to `main`), `claude.yml` and `claude-code-review.yml` (Claude GitHub Actions, triggered by `@claude` mentions)

## Platform Requirements

**Development:**
- Python 3.12+ with `uv` (backend); Node.js 24 with npm (frontend)
- Docker for the standard run path and for E2E (`test/docker-compose.test.yml`)
- Optional: a browser with EventSource support (all modern browsers)
- Port 8000 free on localhost

**Production:**
- Single container (`finally`) exposing port 8000; serves API, SSE and static frontend
- Persistent volume at `/app/db` for `finally.db`
- Healthcheck: `GET /api/health` (Dockerfile `HEALTHCHECK`, every 30s)
- Target platforms per `planning/PLAN.md`: local Docker; optional AWS App Runner, Render, or any container platform

---

*Stack analysis: 2026-11-04*
