---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# Testing Patterns

**Analysis Date:** 2026-11-04

## Test Framework

The project has three test layers: backend unit/API tests (pytest), frontend unit/component tests (Vitest), and end-to-end tests (Playwright). No CI workflow runs any of them; `.github/workflows/blank.yml` is a placeholder that only echoes a message.

**Backend (Python):**
- Runner: pytest `>=8.3.0` (optional `dev` extra in `backend/pyproject.toml`)
- Async: `pytest-asyncio >=0.24.0` with `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"`. Async tests need no decorator.
- Coverage: `pytest-cov >=5.0.0`; `[tool.coverage.run] source = ["app"]`, `omit = ["tests/*"]`.
- Lint of tests: Ruff, same config as app code (`backend/pyproject.toml`).
- Config: `backend/pyproject.toml` (`[tool.pytest.ini_options]`).
- Assertion library: plain `assert` with pytest helpers `pytest.raises(..., match=...)` and `pytest.approx(...)`.

**Frontend (TypeScript):**
- Runner: Vitest `^5.1.0` (`frontend/package.json`, script `"test": "vitest run"`).
- Environment: `jsdom` (`^30.1.3`).
- Testing library: `@testing-library/react ^16.3.3`, `@testing-library/dom ^10.4.2`, `@testing-library/user-event ^14.6.8`, `@testing-library/jest-dom ^7.0.1`.
- Config: `frontend/vitest.config.mts` (uses `@vitejs/plugin-react` and the `@` alias).
- Assertion library: Vitest `expect` extended with jest-dom matchers (`toHaveTextContent`, `toHaveClass`, `toHaveAttribute`, `toBeDisabled`, `toBeInTheDocument`).

**End-to-end (Playwright):**
- Runner: `@playwright/test` `1.64.1` in `test/package.json` (script `"test": "playwright test"`).
- Config: `test/playwright.config.ts`.
- Browser project: `chromium` only, Desktop Chrome device with a 1600x1000 viewport.

## Run Commands

```bash
# Backend (run from backend/)
uv sync --extra dev                              # Install dev dependencies
uv run --extra dev pytest -v                     # All tests
uv run --extra dev pytest tests/chat -v          # One package
uv run --extra dev pytest --cov=app              # With coverage
uv run --extra dev ruff check app/ tests/        # Lint

# Frontend (run from frontend/)
npm test                                         # vitest run (single pass)
npx vitest                                       # Watch mode (default in a TTY)

# E2E (run from test/, server must be on BASE_URL, default http://localhost:8000)
npm install
npx playwright install chromium
npx playwright test                              # All E2E specs, serially
```

Docker-based E2E (the recommended path, per `test/README.md`):
```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down
```
The app container runs with `LLM_MOCK=true` and a tmpfs database, so every run starts from a fresh seeded state.

## Test File Organization

**Backend location:** tests live in `backend/tests/`, mirroring `backend/app/` subpackages. Each directory has an empty `__init__.py`.

```
backend/tests/
├── conftest.py                 # Shared db_conn fixture (temp SQLite)
├── api/test_routes.py          # Full app via TestClient (real lifespan)
├── chat/
│   ├── conftest.py             # FakeSource, mock_mode, chat client fixtures
│   ├── test_llm.py             # LiteLLM call args, parsing, mock switch
│   ├── test_mock.py            # Canned mock responses
│   └── test_router.py          # POST /api/chat end to end
├── db/test_db.py
├── market/
│   ├── test_cache.py
│   ├── test_factory.py
│   ├── test_interface.py       # ABC conformance for both sources
│   ├── test_massive.py         # Massive parsing and polling
│   ├── test_models.py
│   ├── test_simulator.py       # GBM simulator
│   ├── test_simulator_source.py
│   └── test_stream.py          # SSE frames
├── portfolio/test_service.py
└── watchlist/test_service.py
```

**Backend naming:**
- Files: `test_<module>.py` matching the app module under test (`app/market/simulator.py` → `tests/market/test_simulator.py`).
- Functions: `test_<behavior>` in snake_case, describing the rule: `test_sell_at_loss_keeps_avg_cost`, `test_insufficient_cash`, `test_watchlist_changes_run_before_trades`.
- Classes: optional, prefixed `Test` (`class TestGBMSimulator`, `class TestParseSnapshot` in `tests/market/`). Use a class to group related tests of one unit; use top-level functions otherwise (most of `tests/portfolio/test_service.py`).

**Frontend location:**
- Component tests are colocated with components: `frontend/components/components.test.tsx` (one file covering all tracked components).
- Library tests are colocated with the lib modules: `frontend/lib/lib.test.ts` (tests `applyLivePrices`, `sessionChangePercent`, `toChartData`, `treemap`).
- Setup: `frontend/test/setup.ts` (imports `@testing-library/jest-dom/vitest`, registers `afterEach(() => cleanup())`).
- Include glob: `**/*.test.{ts,tsx}`; excludes `node_modules`, `out`, `.next`.

**E2E location:** `test/tests/` with ordered specs and a shared `helpers.ts`:
- `01-fresh-start.spec.ts`: default state on a fresh database.
- `02-api.spec.ts`: REST contract via the Playwright `request` fixture.
- `03-ui.spec.ts`: browser flows (add/remove watchlist, trade, portfolio, chat).

## Test Structure

**Backend suite pattern** (from `backend/tests/portfolio/test_service.py`):
```python
@pytest.fixture
def cache():
    c = PriceCache()
    c.update("AAPL", 100.0)
    c.update("MSFT", 400.0)
    return c


def test_buy_creates_position_and_debits_cash(db_conn, cache):
    trade = execute_trade(db_conn, cache, "aapl", "buy", 10)
    assert trade["ticker"] == "AAPL" and trade["price"] == 100.0 and trade["side"] == "buy"
    p = get_portfolio(db_conn, cache)
    assert p["cash_balance"] == 9000.0
    assert _count(db_conn, "trades") == 1
```
- Arrange with fixtures, act with one call, assert several related facts on one line or a few lines.
- Helper `_count(conn, table)` is defined locally in the test module when needed; do not put shared helpers in `conftest.py` unless used by multiple packages.

**Parametrized validation tests:**
```python
@pytest.mark.parametrize("ticker,side,qty,msg", [
    ("AAPL", "buy", 0, "greater than 0"),
    ("BAD1", "buy", 1, "Invalid ticker"),
    ("NFLX", "buy", 1, "No price available"),
])
def test_validation_errors(db_conn, cache, ticker, side, qty, msg):
    with pytest.raises(TradeError, match=msg):
        execute_trade(db_conn, cache, ticker, side, qty)
```
Use `match=` with the user-facing message substring; it doubles as a check that the error text is meaningful.

**API route tests** (from `backend/tests/api/test_routes.py`): the real app is imported (`from app import main`) and wrapped in `TestClient` as a context manager so lifespan runs. Each test sets `FINALLY_DB_PATH` to a `tmp_path` database and clears the module-level price cache first.
```python
@pytest.mark.parametrize("body,status", [
    ({"ticker": "AAPL", "quantity": 1000, "side": "buy"}, 400),
    ({"ticker": "AAPL", "quantity": 1, "side": "short"}, 422),
])
def test_trade_errors(client, body, status):
    r = client.post("/api/portfolio/trade", json=body)
    assert r.status_code == status
    assert "detail" in r.json()
```

**Async tests:** write them as `async def test_...` with no marker (auto mode). Use `asyncio.create_task` plus `asyncio.sleep` for background loops, and cancel the task at the end:
```python
async def test_snapshot_loop_records(db_conn):
    task = asyncio.create_task(main.snapshot_loop(interval=0.01))
    await asyncio.sleep(0.1)
    task.cancel()
    assert db_conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] >= 2
```

**Frontend component pattern** (from `frontend/components/components.test.tsx`):
- `describe` per component, `it` per behavior, with names that state the behavior: `it("flashes green on uptick and red on downtick, then clears", ...)`.
- Render with `render(...)`, query with `screen.getByTestId(...)`, assert with jest-dom matchers.
- Build test data as typed constants at the top of the file (`const positions: Position[] = [...]`), importing types from `@/lib/types`.
- For tests that need a re-render with new props, return a `rerender`-friendly helper that returns JSX (`function row(price: number | null) { return (<table>...</table>); }`).
- Wrap wrapper-less components that render `<tr>` in a `<table><tbody>` in the helper.

**Timers:** use fake timers around the behavior under test, and restore them at the end of the test:
```ts
vi.useFakeTimers();
rerender(row(101));
expect(cell).toHaveClass("flash-up");
act(() => vi.advanceTimersByTime(500));
expect(cell.className).not.toMatch(/flash-/);
vi.useRealTimers();
```

**User interaction:** use `userEvent` (not `fireEvent`) and `await` each action:
```ts
await userEvent.type(screen.getByTestId("chat-input"), "hello");
await userEvent.click(screen.getByTestId("chat-send"));
expect(onSend).toHaveBeenCalledWith("hello");
```

**E2E pattern** (from `test/tests/02-api.spec.ts` and `test/tests/03-ui.spec.ts`):
- `test.describe("API contract", ...)` groups related API tests; `test.describe.configure({ mode: "serial" })` is used where state carries between tests.
- Locate elements only by `data-testid`: `page.getByTestId("trade-ticker").fill(ticker)`.
- Wait with auto-retrying assertions, not sleeps: `await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected")`.
- Use `expect.poll(...)` for backend state that updates asynchronously (see `waitForPrice` in `test/tests/helpers.ts`).
- Shared helpers in `test/tests/helpers.ts`: `DEFAULT_TICKERS`, `getPortfolio(request)`, `waitForPrice(request, ticker)`, `heldQuantity(request, ticker)`, `removeIfWatched(request, ticker)`. Put reusable setup there, not in spec files.
- Cleanup of shared state is done inline at the start of a test (`await removeIfWatched(request, "PYPL")`) so specs can run against a previously-used database.

## Setup and Teardown

**Backend:**
- `db_conn` (`backend/tests/conftest.py`): sets `FINALLY_DB_PATH` to `tmp_path / "test.db"` with `monkeypatch`, runs `init_db()`, yields an open connection, closes it afterward. Use this for any test that touches the database.
- `tests/chat/conftest.py` `client` fixture: builds a bare `FastAPI()` with only `create_chat_router(cache, source)` and shares the same temp DB via `db_conn`.
- `mock_mode` fixture: sets `LLM_MOCK=true` and removes `OPENAI_API_KEY` via `monkeypatch`.
- `tests/conftest.py` also defines an `event_loop_policy` fixture returning `asyncio.DefaultEventLoopPolicy()`; pytest-asyncio is in auto mode so this is rarely needed.

**Frontend:**
- `frontend/test/setup.ts` calls RTL `cleanup()` after each test. Do not call `cleanup` manually in test files.
- Timers are restored with `vi.useRealTimers()` at the end of each timer test. If an assertion fails before that line, timers leak to later tests; wrap in `try/finally` only if a new test needs it.

**E2E:**
- No per-test teardown; the database is reset by restarting the container (tmpfs volume). Within a run, tests are serial (`workers: 1`, `fullyParallel: false`) and use the shared database.

## Mocking

**Backend mocking approach:** monkeypatch module attributes for the LLM and external SDK calls; use `unittest.mock` only for SDK client objects that are replaced wholesale.

**Replacing a module-level async function** (from `backend/tests/chat/test_router.py`):
```python
def fake_llm(monkeypatch, response=None, error=None, seen=None):
    async def _fake(messages, user_message):
        if seen is not None:
            seen.append(messages)
        if error:
            raise error
        return response

    monkeypatch.setattr(chat_router, "get_llm_response", _fake)
```

**Replacing a third-party call** (from `backend/tests/chat/test_llm.py`):
```python
monkeypatch.setattr(llm.litellm, "acompletion", fake_completion(content, calls))
```
Record call kwargs in a list and assert on them, e.g. `kwargs["response_format"] is LLMResponse` and `"temperature" not in kwargs`.

**Replacing an SDK client with `MagicMock`** (from `backend/tests/market/test_massive.py`):
```python
source = MassiveDataSource("test-key", cache or PriceCache(), poll_interval=poll_interval)
source._tickers = list(tickers)
source._client = MagicMock()
```
`patch` is used for the same kind of substitution in `backend/tests/market/test_simulator.py` (`from unittest.mock import patch`).

**Fakes for abstract interfaces** (from `backend/tests/chat/conftest.py`): implement the ABC in a small in-memory class rather than mocking it. `FakeSource(MarketDataSource)` tracks tickers in a list and writes a fixed price to the cache on `add_ticker`. Prefer this for any test that needs a `MarketDataSource`.

**Real SDK models instead of mocks:** `backend/tests/market/test_massive.py` builds snapshots with the real `massive` SDK model (`TickerSnapshot.from_dict(...)`) so attribute names are checked against the actual library. Follow this pattern when parsing third-party payloads.

**Environment variables:** always use `monkeypatch.setenv` / `monkeypatch.delenv`, never `os.environ` directly, so values are restored after each test.

**Frontend mocking:** `vi.fn()` for callbacks (`const onSend = vi.fn();` then `expect(onSend).toHaveBeenCalledWith("hello")`). No module mocks are currently used.

**E2E mocking:** no browser-side mocking. Deterministic chat behavior comes from `LLM_MOCK=true` in the app container; the backend mock rules are in `backend/app/chat/mock.py` (`buy`, `sell`, `watch`, anything else).

**What to mock:**
- External LLM calls (`litellm.acompletion`) and the Massive REST client.
- Time-based background loops: drive them with short intervals (e.g. `snapshot_loop(interval=0.01)`) rather than mocking `asyncio.sleep`.
- Browser `EventSource` is not mocked; component tests pass data as props.

**What NOT to mock:**
- The SQLite database. Tests use a real temporary database through `db_conn`.
- `PriceCache`. Tests construct a real one and call `update` / `remove`.
- Domain services (`execute_trade`, `add_ticker`). Test them through the real code path.
- The FastAPI app in route tests. `test_routes.py` runs the real lifespan.

## Fixtures and Factories

**Backend test data:**
- Seed prices come from `backend/app/market/seed_prices.py` (`SEED_PRICES`, `DEFAULT_PARAMS`, `UNKNOWN_SEED_RANGE`); simulator tests import these constants rather than duplicating numbers.
- Default tickers come from `backend/app/db/connection.py` (`DEFAULT_TICKERS`) and are re-exported where used in tests (`from app.db import DEFAULT_TICKERS`).
- Price fixture constant in chat tests: `PRICE = 100.0` in `backend/tests/chat/conftest.py`; tests import it (`from tests.chat.conftest import PRICE`).
- Inline dict/list literals are the normal form of test data; there is no factory library.

**Frontend test data:** typed literals at the top of the test file (`positions: Position[]`, `messages: ChatMessage[]`), plus a `Portfolio` literal in `frontend/lib/lib.test.ts`.

**E2E test data:** none seeded by tests; they rely on the fresh database state and use `DEFAULT_TICKERS` from `test/tests/helpers.ts`. Use unique ticker symbols such as `PYPL` for add/remove scenarios and clean them up with `removeIfWatched`.

**Location summary:**
- Backend shared fixtures: `backend/tests/conftest.py`, plus package-level `conftest.py` (currently `backend/tests/chat/conftest.py`).
- Frontend setup: `frontend/test/setup.ts`.
- E2E helpers: `test/tests/helpers.ts`.

## Coverage

**Requirements:** None enforced. No `fail_under` is set in `backend/pyproject.toml`, and no coverage threshold exists for Vitest or Playwright.

**Backend coverage config:**
- Source: `app` (`[tool.coverage.run] source = ["app"]`), tests omitted.
- Excluded lines: `pragma: no cover`, `__repr__`, `raise AssertionError`, `raise NotImplementedError`, `if __name__ == "__main__":`, `if TYPE_CHECKING:`.

**View coverage:**
```bash
cd backend && uv run --extra dev pytest --cov=app --cov-report=term-missing
```

**Frontend coverage:** not configured. Add `--coverage` with `@vitest/coverage-v8` only if needed; it is not in `frontend/package.json` today.

## Test Types

**Unit tests (backend):** service and model logic with a real temp DB and in-memory cache. Examples: `tests/portfolio/test_service.py` (trade math, weighted average cost, dust deletion), `tests/market/test_simulator.py` (GBM properties, prices stay positive), `tests/market/test_cache.py`.

**Interface conformance tests:** `tests/market/test_interface.py` asserts both sources subclass `MarketDataSource`, implement every abstract method as coroutine functions (except `get_tickers`), and expose the exact `__all__` from `app.market`. Add to this file when a new abstract method or a new source is added.

**API / integration tests (backend):** `tests/api/test_routes.py` exercises status codes and response shapes through HTTP using the real app, real simulator and a temp DB. `tests/chat/test_router.py` covers the full chat flow including auto-execution and storage.

**Component tests (frontend):** rendering with mock props, price-flash timing, empty states, form submission, loading states, and inline action text. Targets the behaviors listed in PLAN §12.

**E2E tests:** `test/tests/` runs the built app in Chromium against `LLM_MOCK=true`:
- Fresh start: defaults, `$10,000.00` cash, connected status, changing prices.
- Watchlist add/remove, trades (buy/sell), portfolio display, chat with the mocked response, SSE reconnection.
- The API spec checks exact key sets for watchlist items (`Object.keys(aapl).sort()`), so adding or removing response fields requires updating that spec.

**Not present:** frontend integration tests against the real backend (E2E covers this), load tests, visual regression tests, and automated tests for the Massive live API (the Massive client is tested with synthetic SDK objects only).

## Common Patterns

**Async backend test with a background task:**
```python
task = asyncio.create_task(main.snapshot_loop(interval=0.01))
await asyncio.sleep(0.1)
task.cancel()
```
Always cancel background tasks at the end of the test.

**Error path (backend):**
```python
with pytest.raises(TradeError, match="Insufficient cash"):
    execute_trade(db_conn, cache, "MSFT", "buy", 101)
assert _count(db_conn, "trades") == 0   # nothing was written
```
Every error test should also assert that no side effects were persisted.

**Error path (HTTP):**
```python
r = client.post("/api/watchlist", json={"ticker": "PYPL"})
assert r.status_code == 400
```
Assert the status code first, then the body shape (`"detail" in r.json()`).

**Error path (frontend):** `expect(screen.getByTestId("watchlist-error")).toHaveTextContent(...)` after a rejected promise from a mocked callback.

**Error path (E2E):** check the UI state and the backend state (`heldQuantity`, `getPortfolio`) together after a failed action.

**Async UI assertions (E2E):**
```ts
await expect(price).not.toHaveText(first!);
await expect.poll(async () => ...).not.toBeNull();
```
Prefer `expect` with built-in retry over fixed waits.

## Gaps and Conventions to Keep

- Frontend tests live in `frontend/lib/` but the root `.gitignore` pattern `lib/` excludes that directory from git. Confirm `frontend/lib/lib.test.ts` is tracked before relying on it in CI. See CONCERNS.md.
- No CI job runs `pytest`, `vitest`, or Playwright.
- When adding a backend test, follow the existing `tests/<package>/test_<module>.py` path, add `__init__.py` if a new package directory is created, and reuse `db_conn` for DB work.
- When adding a frontend component test, add it to the colocated `*.test.tsx` file and use `data-testid` selectors already present in the component.
- When adding an E2E scenario, number the file to keep the serial order (`04-...spec.ts`) and keep state changes reversible.

---

*Testing analysis: 2026-11-04*
