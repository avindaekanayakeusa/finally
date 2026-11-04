---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# External Integrations

**Analysis Date:** 2026-11-04

## APIs & External Services

**LLM (OpenAI via LiteLLM):**
- OpenAI Chat Completions, model `openai/gpt-5-mini`, called through `litellm.acompletion` in `backend/app/chat/llm.py`
  - SDK/Client: `litellm` `1.108.0` (locked)
  - Auth: `OPENAI_API_KEY` env var (read by LiteLLM; the app never reads it when `LLM_MOCK=true`)
  - Request options: `response_format=LLMResponse` (Pydantic structured output, `backend/app/chat/schema.py`), `reasoning_effort="low"`; no `temperature`/`top_p`
  - Response parsed with `LLMResponse.model_validate_json` in `backend/app/chat/llm.py`; failures surface as 502 from `backend/app/chat/router.py`
  - Mock alternative: `backend/app/chat/mock.py` (deterministic responses, selected by `LLM_MOCK=true`)
- Guidance for new LLM code: `.claude/skills/openai-llm/SKILL.md` (referenced by `CLAUDE.md`)

**Market Data (Massive, formerly Polygon.io) - optional:**
- REST polling of snapshot data for all tracked tickers, implemented in `backend/app/market/massive_client.py`
  - SDK/Client: `massive` `2.2.0` (locked), `massive.RESTClient`; errors `massive.exceptions.AuthError`, `BadResponse`
  - Auth: `MASSIVE_API_KEY` env var; enabling is done in `backend/app/market/factory.py`
  - Poll cadence: `MASSIVE_POLL_INTERVAL` seconds (default 15, min 1; README guidance: free tier 5 req/min needs >= 15)
  - Parsing: `parse_snapshot` in `backend/app/market/massive_client.py` picks price from last trade -> minute close -> day close -> previous day close; timestamps converted from nanoseconds
- Not used when `MASSIVE_API_KEY` is empty; `test/docker-compose.test.yml` forces it empty

**Market Data Simulator (built-in, no external service):**
- GBM price generator in `backend/app/market/simulator.py` using `numpy` (`np.random.default_rng`)
- Seed prices in `backend/app/market/seed_prices.py`; default for all runs without `MASSIVE_API_KEY`

## Data Storage

**Databases:**
- SQLite (single file) - the only persistent store
  - Path: `<repo>/db/finally.db` (container: `/app/db/finally.db`), override `FINALLY_DB_PATH` (`backend/app/db/connection.py`)
  - Schema: `backend/db/schema.sql` (idempotent `CREATE TABLE IF NOT EXISTS`), applied on every startup by `init_db()` in `backend/app/main.py` lifespan
  - Seeding: `_seed()` in `backend/app/db/connection.py` inserts the `default` user ($10,000) and 10 default watchlist tickers
  - Client: Python stdlib `sqlite3`, `sqlite3.Row` rows, one connection per call via `get_connection()`; no ORM
  - Tables: `users_profile`, `watchlist`, `positions`, `trades`, `portfolio_snapshots`, `chat_messages`
- Ticker access helper: `backend/app/db/tickers.py`

**File Storage:**
- Local filesystem only (the SQLite file and the static frontend bundle served from `backend/static/`)

**Caching:**
- In-process only: `PriceCache` in `backend/app/market/cache.py` (latest price, previous price, timestamp, version counter). No Redis or external cache.

## Authentication & Identity

**Auth Provider:**
- None. Per `planning/PLAN.md`, there is no login or API auth; all requests act as user `"default"` (`DEFAULT_USER` in `backend/app/db/connection.py`).
- Secrets are only the `OPENAI_API_KEY` and `MASSIVE_API_KEY` values, supplied via environment.

## Monitoring & Observability

**Error Tracking:**
- None detected (no Sentry or similar SDK in `backend/pyproject.toml` or `frontend/package.json`)

**Logs:**
- Python `logging` to stdout with `basicConfig(level=INFO)` in `backend/app/main.py`; module loggers used in market, chat and snapshot code
- Frontend: no logging library detected

**Health:**
- `GET /api/health` returns `{"status": "ok"}` (`backend/app/main.py`); used by the Dockerfile `HEALTHCHECK` and by `test/docker-compose.test.yml`

## CI/CD & Deployment

**Hosting:**
- Docker container, run locally via `scripts/start_mac.sh` / `scripts/start_windows.ps1` (`docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally`) or `docker-compose.yml`
- Optional deploy targets named in `planning/PLAN.md`: AWS App Runner, Render, any container platform. No deploy config (Terraform, `deploy/`) present in the repo.

**CI Pipeline:**
- GitHub Actions in `.github/workflows/`:
  - `blank.yml` - placeholder "CI" job (echo steps only; no build or test)
  - `claude.yml` - Claude Code action triggered by `@claude` in issues, PR comments and reviews
  - `claude-code-review.yml` - Claude automated code review on PRs
- E2E: `test/docker-compose.test.yml` builds the app and runs Playwright in `mcr.microsoft.com/playwright:v1.64.1-noble` against `http://finally:8000`
- Container registry: none configured. Base images pulled from Docker Hub (`node:24-slim`, `python:3.13-slim`) and `ghcr.io/astral-sh/uv:0.13.6`, and `mcr.microsoft.com/playwright`.

## Environment Configuration

**Required env vars:**
- `OPENAI_API_KEY` - required for live chat unless `LLM_MOCK=true`
- None required for the app to start; the rest of the app works without a key

**Optional env vars:**
- `MASSIVE_API_KEY` - enables Massive market data
- `MASSIVE_POLL_INTERVAL` - Massive poll seconds
- `LLM_MOCK` - deterministic chat responses
- `FINALLY_DB_PATH` - SQLite path override
- `BACKEND_URL` - frontend dev proxy target only

**Secrets location:**
- `.env` at repo root (gitignored); `.env.example` is the committed template. Passed to the container via `--env-file` (scripts) or `env_file` (`docker-compose.yml`). Not read or recorded in this analysis.

## Webhooks & Callbacks

**Incoming:**
- None. The app exposes only same-origin REST and SSE endpoints (see below).
  - `GET /api/stream/prices` - SSE price stream (`backend/app/market/stream.py`), consumed by `frontend/hooks/usePriceStream.ts` via `EventSource`
  - `GET /api/portfolio`, `POST /api/portfolio/trade`, `GET /api/portfolio/history` - `backend/app/portfolio/routes.py`
  - `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{ticker}` - `backend/app/watchlist/routes.py`
  - `POST /api/chat` - `backend/app/chat/router.py`
  - `GET /api/health` - `backend/app/main.py`
  - Frontend client wrapper: `frontend/lib/api.ts` (`fetch` to same-origin paths)

**Outgoing:**
- Massive REST API calls when `MASSIVE_API_KEY` is set (polling, `backend/app/market/massive_client.py`)
- OpenAI API calls via LiteLLM for chat when `LLM_MOCK` is not `true` (`backend/app/chat/llm.py`)
- No webhooks registered

---

*Integration audit: 2026-11-04*
