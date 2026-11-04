# Agent Team — Ownership & Interfaces

All agents share one working tree on branch `agent-teams`. Stay inside your owned paths.
Do not commit; the lead commits. Coordinate via messages, not by editing others' files.
`planning/PLAN.md` is the source of truth for behavior and response shapes (§8).

## Ownership

| Agent | Owns |
|---|---|
| `db-engineer` | `backend/db/` (schema SQL, seed), `backend/app/db/`, `backend/app/portfolio/`, `backend/app/watchlist/`, `backend/app/main.py` (lifespan, router wiring, `/api/health`, snapshot task, static mount), `backend/tests/` for those |
| `llm-engineer` | `backend/app/chat/` (prompt, schema, LiteLLM call, mock, chat route), `backend/tests/chat/` |
| `frontend-engineer` | `frontend/` |
| `devops-engineer` | `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `scripts/`, `.env.example`, `db/.gitkeep`, `.gitignore`, `README.md` |
| `integration-tester` | `test/` (Playwright + `docker-compose.test.yml`) |

`backend/pyproject.toml` / `uv.lock`: change only via `uv add` (db-engineer and llm-engineer both may).

## Backend seams (db-engineer provides, llm-engineer consumes)

Module `app.portfolio.service` (sync functions, take a sqlite3 connection + PriceCache):

- `get_portfolio(conn, cache) -> dict` — §8 `GET /api/portfolio` shape
- `execute_trade(conn, cache, ticker, side, quantity) -> dict` — returns the `trade` dict; raises `TradeError(str)` on business-rule failure
- After trades/watchlist changes, call `sync_tracked_tickers(conn, source)` so the market source tracks watchlist ∪ positions

Module `app.watchlist.service`:

- `list_watchlist(conn, cache) -> list[dict]`
- `add_ticker(conn, cache, source, ticker) -> dict` / `remove_ticker(conn, source, ticker)` — raise `WatchlistError(str)` (duplicate/invalid) and `WatchlistNotFound(str)`

Module `app.db`: `get_connection()` and `init_db()`; DB path `../db/finally.db` relative to `backend/` (override via `FINALLY_DB_PATH` env var for tests).

llm-engineer exposes `create_chat_router(cache, source) -> APIRouter` in `app.chat`; db-engineer mounts it in `main.py`.
Exact signatures may be refined by db-engineer — announce any change to llm-engineer.

## Done criteria

- Backend: `cd backend && uv run --extra dev pytest` green, `ruff check` clean
- Frontend: `npm run build` produces `frontend/out/`, unit tests green
- Docker: `scripts/start_windows.ps1` brings app up on http://localhost:8000
- E2E: `test/` Playwright suite green against the container with `LLM_MOCK=true`
