---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# Coding Conventions

**Analysis Date:** 2026-11-04

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` inside feature packages, e.g. `backend/app/portfolio/service.py`, `backend/app/chat/execute.py`, `backend/app/market/massive_client.py`.
- Python package entry points: `__init__.py` re-exports the public API (`backend/app/market/__init__.py` defines `__all__`).
- React components: `PascalCase.tsx`, one component per file, e.g. `frontend/components/Watchlist.tsx`, `frontend/components/TradeBar.tsx`.
- Hooks: `camelCase.ts` with `use` prefix, in `frontend/hooks/` (e.g. `frontend/hooks/usePriceStream.ts`, `frontend/hooks/useTerminal.ts`).
- Library modules: `camelCase.ts` in `frontend/lib/` (e.g. `frontend/lib/api.ts`, `frontend/lib/format.ts`, `frontend/lib/treemap.ts`).
- Tests: `test_*.py` (backend, see TESTING.md); `*.test.tsx` / `*.test.ts` (frontend); `NN-name.spec.ts` (E2E in `test/tests/`).

**Functions (Python):**
- `snake_case`, verb-first: `execute_trade`, `get_portfolio`, `record_snapshot`, `sync_tracked_tickers`, `validate_ticker`.
- Module-private helpers are prefixed with `_`: `_position_dict`, `_apply_buy`, `_apply_sell`, `_get_position`, `_entry`, `_parse`, `_apply_watchlist_change`.
- Async functions use `async def` with no special suffix: `add_ticker`, `execute_actions`, `get_llm_response`.

**Functions (TypeScript):**
- `camelCase`; React components are named function exports (`export function Header`).
- Event handlers inside components are named by action, not `handleX`: `submit`, `trade`, `sendChat`, `addTicker`, `removeTicker` (see `frontend/components/Watchlist.tsx`, `frontend/hooks/useTerminal.ts`).

**Variables:**
- Python: `snake_case`; module-level constants are `UPPER_SNAKE_CASE` (`DUST`, `HISTORY_LIMIT`, `SNAPSHOT_INTERVAL`, `DEFAULT_USER`, `DEFAULT_CASH`, `DEFAULT_TICKERS`, `MODEL`, `SYSTEM_PROMPT`). Compiled regexes are `_TICKER_RE`.
- TypeScript: `camelCase`; module constants `UPPER_SNAKE_CASE` (`MAX_POINTS`, `HISTORY_REFRESH_MS`); lookup tables `UPPER_CASE` (`DOT` in `frontend/components/Header.tsx`).
- Logger variable is always `logger = logging.getLogger(__name__)`.

**Types and classes:**
- Python classes `PascalCase`; exceptions end in `Error` or describe the condition: `TradeError`, `WatchlistError`, `WatchlistNotFound` (`backend/app/watchlist/service.py`). Request/response models are suffixed by intent: `TradeRequest`, `WatchlistAdd`, `ChatRequest`, `LLMResponse`, `TradeInstruction`, `WatchlistInstruction`.
- TypeScript interfaces are `PascalCase` without an `I` prefix (`Position`, `ChatMessage`, `PriceStream`). Component prop types are always named `Props` and declared as a local `interface Props` directly above the component.
- Shared API/domain types live in `frontend/lib/types.ts` and mirror the backend JSON shapes from PLAN §8.

**JSON / wire field names:**
- All API JSON uses `snake_case` (`cash_balance`, `avg_cost`, `previous_price`, `executed_at`). The frontend types match these names exactly; do not camelCase API fields.
- Tickers are always uppercase strings. Timestamps in REST responses are ISO 8601 UTC ending in `Z` (`now_iso()` in `backend/app/db/connection.py`). SSE `timestamp` is Unix seconds.

**Test IDs (frontend):**
- `data-testid` values are kebab-case, with the ticker appended when a row is per-symbol: `watchlist-row-AAPL`, `price-AAPL`, `position-row-TSLA`, `heatmap-cell-AAPL`, `trade-buy`, `chat-send`.
- State is exposed via data attributes, not classes: `data-status="connected"`, `data-pnl="profit"`.

## Code Style

**Python formatting and linting:**
- Ruff is the only Python linter/formatter configured, in `backend/pyproject.toml`:
  - `line-length = 100`, `target-version = "py312"`.
  - Lint rules: `select = ["E", "F", "I", "N", "W"]`, `ignore = ["E501"]` (long lines are tolerated; the formatter handles wrapping).
- Run: `uv run --extra dev ruff check app/ tests/` (from `backend/`).
- Python version: `>=3.12` (the Dockerfile uses Python 3.13 slim).
- Every module begins with a one-line module docstring, then `from __future__ import annotations` (used consistently in `backend/app/**`).
- Use double quotes; trailing commas on multi-line literals and argument lists.
- Use `# noqa: N818` only when a name is fixed by the planning contract (`WatchlistNotFound` in `backend/app/watchlist/service.py`).

**TypeScript formatting and linting:**
- No ESLint, Prettier, or Biome config is present in the repo (`frontend/` and `test/`). Match the existing style by hand: double quotes, semicolons, 2-space indent, trailing commas in multi-line objects.
- TypeScript `strict: true` (`frontend/tsconfig.json`), `moduleResolution: "bundler"`, `isolatedModules: true`.
- Use `import type { ... }` for type-only imports (e.g. `frontend/components/Watchlist.tsx`, `frontend/hooks/useTerminal.ts`).
- Long Tailwind class strings are kept on one line inside `className`; for layout shapes, multi-line JSX attributes are used.

**Comments:**
- Python: docstrings on nearly every function and class. Comments are sparse; use them only for non-obvious intent (e.g. `# noqa`, a tricky invariant).
- TypeScript: a single-line JSDoc `/** ... */` above each exported component, hook and lib function, e.g. `/** Market order entry: ticker, quantity, buy and sell buttons. */` in `frontend/components/TradeBar.tsx`.

## Import Organization

**Python order** (ruff `I` rules, enforced):
1. Standard library (`import sqlite3`, `import asyncio`, `from datetime import UTC, datetime`).
2. Third-party (`from fastapi import APIRouter`, `from pydantic import BaseModel`, `import litellm`).
3. First-party absolute imports from the `app` package (`from app.db import ...`, `from app.market import PriceCache`).
4. Relative imports within the same feature package (`from .service import ...`, `from .schema import ...`).

Example from `backend/app/portfolio/routes.py`:
```python
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import get_db, sync_tracked_tickers
from app.market import MarketDataSource, PriceCache

from .service import TradeError, execute_trade, get_history, get_portfolio
```

**TypeScript order** (observed convention):
1. React / library imports (`import { useEffect, useState } from "react";`).
2. Path-aliased project imports using `@/` (`@/lib/api`, `@/lib/types`, `@/hooks/usePriceStream`).
3. Sibling component imports with `./` (`./PanelTitle`, `./WatchlistRow`).

**Path aliases:**
- `@/*` maps to the `frontend/` root (`frontend/tsconfig.json` `paths`, and `resolve.alias` in `frontend/vitest.config.mts`).
- Python has no alias; import from `app.<package>` and expose public names through the package `__init__.py`.

**Public API via `__init__.py`:**
- Each backend package re-exports its public surface and declares `__all__`. Callers import from the package, not the submodule: `from app.market import PriceCache, create_market_data_source` (see `backend/app/market/__init__.py`, `backend/app/chat/__init__.py`). `backend/tests/market/test_interface.py` asserts the exact `__all__` set.

## Error Handling

**Backend, domain layer:**
- Business-rule failures raise a domain exception that subclasses `Exception` and carries a human-readable message: `TradeError` (`backend/app/portfolio/service.py`), `WatchlistError` and `WatchlistNotFound` (`backend/app/watchlist/service.py`). Services never raise `HTTPException`.
- Validation helpers raise `ValueError` and are wrapped into the domain exception at the service boundary:
  ```python
  def _parse(raw: str) -> str:
      try:
          return validate_ticker(raw)
      except ValueError as e:
          raise WatchlistError(str(e)) from None
  ```
- Chain-suppressing `from None` is used when re-raising a domain error; `from e` is used when the original cause should be kept (`backend/app/chat/router.py`).

**Backend, HTTP layer:**
- Routes translate domain errors to `HTTPException` with the mapped status code and `str(e)` as detail:
  ```python
  try:
      result = execute_trade(conn, cache, body.ticker, body.side, body.quantity)
  except TradeError as e:
      raise HTTPException(400, str(e)) from None
  ```
- Status mapping: business rule → 400, missing watchlist entry → 404, schema validation → 422 (FastAPI default), LLM failure → 502. Error bodies use FastAPI's `{"detail": "..."}` shape only.
- Pydantic `Literal` types enforce enums at the boundary (`side: Literal["buy", "sell"]`), so invalid values become 422 without custom code.

**Backend, action execution (chat):**
- Auto-executed LLM actions never raise to the client for business failures. They are caught per item and returned as `{"status": "failed", "error": str(e)}` alongside executed items (`backend/app/chat/execute.py`). This is the pattern to follow for any batch of user-intent operations.

**Backend, broad exception handlers:**
- `except Exception` is used only at system boundaries where the process must keep running or must convert the error:
  - Background snapshot loop: `logger.exception("Portfolio snapshot failed")` in `backend/app/main.py`.
  - LLM call: `logger.exception("LLM call failed")` then `HTTPException(502, ...)` in `backend/app/chat/router.py`.
  - Market data provider calls in `backend/app/market/massive_client.py` and `backend/app/market/simulator.py`.
- Do not add broad catches inside domain services.

**Backend, transactions:**
- Write paths wrap their statements in `with conn:` so commits and rollbacks are automatic (`execute_trade`, `record_snapshot`, `add_ticker`, `remove_ticker`). A trade writes position, cash, trade row and snapshot inside one `with conn:` block.
- Constraint violations are detected by catching `sqlite3.IntegrityError` and re-raising a domain error (`backend/app/watchlist/service.py`, duplicate add).

**Frontend:**
- The API client throws `Error` with the backend `detail` string when present, otherwise a generic `Request failed (<status>)` (`frontend/lib/api.ts`, `request<T>`).
- User-initiated actions catch and display the message inline:
  ```ts
  try {
    await onAdd(ticker);
    setInput("");
  } catch (err) {
    setError((err as Error).message);
  }
  ```
  Used in `frontend/components/Watchlist.tsx` and `frontend/components/TradeBar.tsx`.
- Background refreshes swallow errors with `.catch(() => {})` (`frontend/hooks/useTerminal.ts`). Use this only for non-critical polling.
- Errors are typed as `(err as Error).message`; there is no custom error class on the frontend.

## Logging

**Backend:**
- Use the stdlib `logging` module with a module-level logger: `logger = logging.getLogger(__name__)` (present in `backend/app/main.py`, `backend/app/chat/router.py`, `backend/app/market/*.py`).
- Global format is configured once in `backend/app/main.py`: `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")`.
- Use `logger.exception(...)` inside `except` blocks to capture the traceback; use `logger.error(...)` for non-exception failures (`backend/app/market/simulator.py`).
- No `print()` in `backend/app/`. Print is limited to standalone demo scripts (`backend/market_data_demo.py`).
- No log lines in frontend code; the frontend uses `console` only implicitly through framework errors.

## Comments

**When to comment:**
- Prefer docstrings. Comments explain *why* only when the reason is not obvious from the code, e.g. the `# noqa: N818` note, or "Guard: the v1 bug read last_trade.timestamp" in tests.
- Inline comments in backend code are rare; trailing comments on constants explain units (`MASSIVE_POLL_INTERVAL` seconds, `# price at the previous update (tick-to-tick)` in `backend/app/market/models.py`).

**Python docstrings:**
- Every public function, class and module has a one-line docstring in imperative or descriptive form, ending with a period: `"""Current cash balance for the user."""`, `"""Fill a market order at the cached price; returns the trade dict."""`.
- Multi-line docstrings add a short body after a blank line, and use indented bullet-style lists only in class docstrings that describe a lifecycle (see `MarketDataSource` in `backend/app/market/interface.py`).
- Docstrings describe the external contract (what a route returns, what raises), not the implementation.

**TypeScript JSDoc:**
- One-line `/** ... */` above each exported symbol, describing what it renders or returns:
  - `/** Top bar: brand, live total value, cash, and SSE connection status. */` (`frontend/components/Header.tsx`)
  - `/** Append each ticker's latest price to its history, capped at MAX_POINTS. */` (`frontend/hooks/usePriceStream.ts`)
- Do not add `@param` tags; the typed signature carries that information.

## Function Design

**Size:**
- Functions are short and single-purpose. Services split work into named private helpers (`execute_trade` delegates to `_apply_buy` / `_apply_sell`, then records the trade and snapshot).
- Route handlers are thin: validate via Pydantic, call a service, translate errors, return a dict.
- React components are small presentational units (`PanelTitle`, `WatchlistRow`, `Stat`) composed inside larger panels. Local helper components live in the same file, unexported (`function Stat(...)` in `frontend/components/Header.tsx`).

**Parameters (Python):**
- Dependencies are passed explicitly, never imported as module singletons inside services: `conn`, `cache`, `source`, `user_id`. Services take `user_id: str = DEFAULT_USER` as the last parameter.
- Route factories receive shared objects: `create_portfolio_router(cache, source)`, `create_chat_router(cache, source)`.
- Keyword-friendly signatures with type hints on all public functions (`-> dict`, `-> list[dict]`, `-> PriceUpdate | None`).

**Parameters (TypeScript):**
- Components take a single `Props` object. Callbacks are named `onX` (`onSelect`, `onRemove`, `onTrade`, `onSend`).
- Async callbacks typed as `Promise<void>` when the parent needs to await them (`onTrade: (...) => Promise<void>` in `frontend/components/TradeBar.tsx`).

**Return values:**
- Python services return plain `dict`/`list[dict]` shaped exactly as the JSON contract (PLAN §8). They do not return Pydantic response models. Build the dict inside the service (`_position_dict`, `_entry`).
- Monetary and quantity math is rounded at the output boundary with `round(x, 2)`; internal math is unrounded.
- Frontend functions return typed values (`Promise<Portfolio>`) via generic helpers (`request<T>`).

## Module Design

**Backend:**
- One feature per package: `app/chat`, `app/portfolio`, `app/watchlist`, `app/market`, `app/db`. Each has `routes.py` (HTTP), `service.py` (logic) where applicable, and `__init__.py` (public exports).
- Cross-package calls go through the public package import (`from app.db import sync_tracked_tickers`), never through another package's private helper.
- Immutable value objects use `@dataclass(frozen=True, slots=True)` (`PriceUpdate` in `backend/app/market/models.py`).
- Abstract interfaces use `abc.ABC` with `@abstractmethod`; implementations live beside the interface (`MarketDataSource` with `SimulatorDataSource` and `MassiveDataSource`).
- Shared mutable state is guarded by `threading.Lock` (`PriceCache` in `backend/app/market/cache.py`).

**Frontend:**
- Barrel files are not used. Import each symbol from its own module (`import { Watchlist } from "@/components/Watchlist"` style, or relative `./Watchlist` from sibling files).
- Pages and layouts are the only `export default` declarations (`frontend/app/page.tsx`, `frontend/app/layout.tsx`). Everything else uses named exports.
- Client-only modules start with `"use client";` (all components using state, hooks, and `EventSource`).
- Shared server state is held in one hook (`useTerminal`) and the live stream in another (`usePriceStream`); components receive data through props rather than reading a global store.

**Barrel files:**
- Python: used, via package `__init__.py` with `__all__`.
- TypeScript: not used.

## Patterns to Follow

**Adding a backend endpoint:**
1. Put business logic in `app/<feature>/service.py` as a function returning a `dict` in the contract shape.
2. Raise a feature-specific exception on rule violation.
3. Add the route inside the feature's `create_<feature>_router(...)` factory in `routes.py`, use `Depends(get_db)` for the connection, translate errors to `HTTPException`.
4. Register the router in `backend/app/main.py` before the static mount.

**Adding a frontend feature:**
1. Add the request to `frontend/lib/api.ts` (`api` object) and the shape to `frontend/lib/types.ts`.
2. Put server-state changes in `frontend/hooks/useTerminal.ts` or a new `use*` hook.
3. Create a `PascalCase.tsx` component with a local `Props` interface, a one-line JSDoc, `data-testid` on interactive elements, and Tailwind classes using the project tokens (`bg-panel`, `border-line`, `text-muted`, `text-up`, `text-down`, `bg-primary`, `text-accent`).

**Color and visual tokens** (Tailwind classes, configured in `frontend/app/globals.css`):
- Backgrounds `bg-bg`, `bg-panel`; borders `border-line`; text `text-muted`; accents `text-accent` (`#ecad0a`), `bg-primary` / `text-primary` (`#209dd7`); price direction `text-up` / `bg-up`, `text-down` / `bg-down`.
- Price flash uses CSS classes `flash-up` and `flash-down`, applied for ~500ms then removed.

## Anti-Patterns (avoid)

- Calling `print()` or adding logs without a module logger in `backend/app/`.
- Returning Pydantic response models from services; keep service output as plain dicts matching the JSON contract.
- Raising `HTTPException` from `service.py` modules.
- Introducing `temperature` or `top_p` in LLM calls (`gpt-5-mini` rejects them; see `backend/app/chat/llm.py`).
- Committing under `frontend/lib/` without checking git: `lib/` is matched by the root `.gitignore` (`lib/` pattern), so `frontend/lib/*.ts` files are present on disk but not tracked. See CONCERNS.md.

---

*Convention analysis: 2026-11-04*
