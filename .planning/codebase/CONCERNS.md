---
last_mapped_commit: 75488e68d2427abfd372374bdccad0e6ddffb9fa
last_mapped_at: 2026-11-04
---
# Codebase Concerns

**Analysis Date:** 2026-11-04

## Summary

| # | Severity | Area | Issue |
|---|----------|------|-------|
| 1 | High | Repo / build | `frontend/lib/` is git-ignored, so a clean clone cannot build |
| 2 | High | Deploy / security | Start scripts and compose publish port 8000 on all interfaces with no auth |
| 3 | High | CI | No automated test or build gate; the only workflow is a placeholder |
| 4 | Medium | Trades | `NaN` quantity crashes the trade route with HTTP 500 (verified) |
| 5 | Medium | Spec gap | Chat history is persisted but cannot be read back; UI loses it on reload |
| 6 | Medium | Chat | LLM call has no timeout and no input size limit |
| 7 | Medium | Frontend perf | Every SSE tick re-renders the whole terminal and resets chart zoom |
| 8 | Medium | Frontend | Errors swallowed silently in several hooks and handlers |
| 9 | Medium | Market data | Massive add-ticker poll shares the global failure backoff |
| 10 | Low | Backend | Blocking SQLite work inside async route handlers and the event loop |
| 11 | Low | Backend | Two ticker validators disagree; money stored as floats |
| 12 | Low | Chat | Trade execution and chat persistence are not one transaction |
| 13 | Low | Ops | Container runs as root; test code and demo script ship in the image |
| 14 | Low | Ops | Start scripts reuse a stale image unless `--build` is passed |
| 15 | Low | Tooling | Broken Stop hook in `Independent reviewer/`; stale review and skill references |

## Build and Repository Integrity

**Frontend lib directory is not tracked by git:**
- Issue: The root `.gitignore` contains `lib/` (line 17, a Python-template pattern). It matches `frontend/lib/`. `git ls-files frontend/lib` returns zero files, so `frontend/lib/api.ts`, `format.ts`, `portfolio.ts`, `treemap.ts`, `types.ts`, and `lib.test.ts` exist only on the author's disk.
- Files: `.gitignore` (line 17), `frontend/lib/*.ts`, `frontend/components/*.tsx` (every component imports `@/lib/...`), `frontend/components/components.test.tsx`
- Impact: On a fresh clone, `npm run build` fails with unresolved imports. The Dockerfile's frontend stage (`COPY frontend/ ./` then `npm run build`) fails too, so the single-container deploy in PLAN §11 cannot be built from the repository. The `frontend/lib` tests cannot run either.
- Fix approach: Add an exception such as `!frontend/lib/` below `lib/` in `.gitignore`, or scope the Python pattern to `backend/`. Then `git add frontend/lib` and verify with `git clone` into an empty directory followed by `docker build .`.

**Planning and review documents are partly stale:**
- Issue: `planning/REVIEW.md` lists findings that no longer match the code. For example, finding 3 says Massive `add_ticker` only registers the ticker, but `backend/app/market/massive_client.py` now polls immediately. Finding 4 says `planning/MARKET_DATA_SUMMARY.md` was deleted, but it is tracked.
- Files: `planning/REVIEW.md`, `CLAUDE.md` (line 5), `README.md` (line 82)
- Impact: Agents that read these documents may chase non-issues or miss real ones.
- Fix approach: Regenerate or delete `planning/REVIEW.md` after the next review pass. Keep the file references in `CLAUDE.md` and `README.md` current.

## Security Considerations

**Port 8000 is published on all host interfaces with no authentication:**
- Risk: `scripts/start_mac.sh` and `scripts/start_windows.ps1` run `-p 8000:8000`, and `docker-compose.yml` maps `"8000:8000"`. Docker binds these to `0.0.0.0`. Anyone on the same network can call `POST /api/portfolio/trade` and `POST /api/chat`, and chat requests spend the operator's `OPENAI_API_KEY`. PLAN §3 states there is no auth by design, so the bind address is the only control.
- Files: `scripts/start_mac.sh`, `scripts/start_windows.ps1`, `docker-compose.yml`, `backend/app/main.py`
- Current mitigation: None. The app has no auth and no host restriction.
- Recommendations: Publish as `127.0.0.1:8000:8000` in both scripts and in `docker-compose.yml`. Document that exposing the port requires adding protection first (PLAN §3 says to add it "if deployed publicly").

**Secrets handling is correct but the key is visible to the container runtime:**
- Risk: `.env` is passed through `--env-file`, so `OPENAI_API_KEY` is readable with `docker inspect`. This is standard for local Docker but worth knowing.
- Files: `scripts/start_mac.sh`, `scripts/start_windows.ps1`, `.env.example`
- Current mitigation: `.env` is git-ignored (`.gitignore`, `.dockerignore`). `backend/app/chat/llm.py` reads the key only through LiteLLM, and `LLM_MOCK=true` skips the call entirely.
- Recommendations: No change required for a local single-user app.

**LLM error text is returned to the browser:**
- Risk: `backend/app/chat/router.py` returns `LLM request failed: {e}` as the 502 `detail`. Provider error strings can include request metadata or internal URLs.
- Files: `backend/app/chat/router.py`
- Current mitigation: The full exception is logged server-side with `logger.exception`.
- Recommendations: Return a fixed message such as `"LLM request failed"` and keep the detail in logs.

**Prompt injection can trigger trades:**
- Risk: The LLM output drives `execute_actions` with no confirmation and no per-request limit (PLAN §9 makes auto-execution deliberate). Any text the model reads, including the user's own message and the portfolio JSON, can produce trades. The stakes are simulated money, so the impact is limited to the simulator, but a Massive-backed setup still uses the same simulated cash.
- Files: `backend/app/chat/execute.py`, `backend/app/chat/context.py`, `backend/app/chat/llm.py`
- Current mitigation: Each trade goes through `execute_trade` validation. Trades are capped by cash and holdings.
- Recommendations: Keep auto-execution as specified. Consider a cap on trades per chat turn if the model starts looping.

## Tech Debt

**CI does not run the test suites:**
- Issue: `.github/workflows/blank.yml` only echoes text. The Claude review workflows run on pull requests but do not run pytest, vitest, or Playwright. The Playwright suite in `test/` runs only when someone runs the compose file by hand.
- Files: `.github/workflows/blank.yml`, `.github/workflows/claude-code-review.yml`, `test/docker-compose.test.yml`
- Impact: Breakages such as concern 1 are not caught before merge. The backend currently passes (242 passed, 1 skipped when run with `uv run pytest`), but nothing enforces that.
- Fix approach: Replace `blank.yml` with a job that runs `cd backend && uv run pytest`, `cd frontend && npm ci && npm test && npm run build`, and the Playwright compose stack.

**Broken Stop hook in a tracked tooling directory:**
- Issue: `Independent reviewer/.claude-plugin/hooks/hooks.json` defines a `Stop` hook whose shell command has an unbalanced quote and a truncated file name (`...write results to a file name...`). The JSON parses, but the shell command does not.
- Files: `Independent reviewer/.claude-plugin/hooks/hooks.json`
- Impact: If the plugin is installed, every session stop runs a failing command. The hook is outside application code, but it is committed at the repository root.
- Fix approach: Complete the command, or remove the plugin from the repository if it is not used.

**Missing LLM skill referenced by the spec:**
- Issue: PLAN §9 tells agents to use `.claude/skills/openai-llm/SKILL.md`. Only `.claude/skills/cerebras` exists.
- Files: `planning/PLAN.md` (§9), `.claude/skills/`
- Impact: Agents writing LLM code have no OpenAI-specific guidance. The code in `backend/app/chat/llm.py` follows the spec, but the guidance it points to is missing.
- Fix approach: Restore the OpenAI skill file or update PLAN §9 to point at the current guidance.

**Module-level side effects in the app entry point:**
- Issue: `backend/app/main.py` creates `price_cache` and `market_source` at import time, reads env vars at import (`create_market_data_source`), and calls `logging.basicConfig` on import.
- Files: `backend/app/main.py`, `backend/app/market/factory.py`
- Impact: Tests and tools that import `app.main` pick up the environment at import time. The factory cannot be re-run with different env vars in one process without reloading modules.
- Fix approach: Build the cache and source inside the lifespan and store them on `app.state`. Keep this change small and cover it with the existing tests.

**Two ticker validators with different rules:**
- Issue: `backend/app/db/tickers.py` (`validate_ticker`) accepts `^[A-Z]{1,5}$`. `backend/app/market/models.py` (`normalize_ticker`) accepts `^[A-Z][A-Z0-9.\-]{0,9}$`. The API uses the first, so a symbol like `BRK.B` is rejected at the API but accepted by the sources.
- Files: `backend/app/db/tickers.py`, `backend/app/market/models.py`
- Impact: Two sources of truth. Changing one without the other produces confusing behavior.
- Fix approach: Use one validator. PLAN §6 specifies 1-5 letters, so the `models.py` pattern should be narrowed to match.

**Money is stored as REAL floats:**
- Issue: `cash_balance`, `avg_cost`, `total_value`, and `price` are SQLite `REAL` (`backend/db/schema.sql`), and arithmetic happens in Python floats (`backend/app/portfolio/service.py`). Repeated buys and sells accumulate rounding error, and `_apply_buy` compares `cash < cost` without tolerance, so an exact-balance buy can fail by a fraction of a cent.
- Files: `backend/db/schema.sql`, `backend/app/portfolio/service.py` (`_apply_buy`, `_apply_sell`, `_adjust_cash`)
- Impact: Small drift in cash over time. Edge-case rejections on exact-balance buys.
- Fix approach: Acceptable for a simulator. If it needs correction, store cents as integers or use `Decimal` at the service boundary.

## Known Bugs

**`NaN` quantity returns HTTP 500 instead of 400 (verified):**
- Symptoms: `POST /api/portfolio/trade` with `"quantity": NaN` (Python's JSON parser accepts the literal) passes Pydantic validation, because `float` accepts NaN by default. `execute_trade` checks `quantity <= 0`, which is False for NaN, and then `_apply_buy` calls `_adjust_cash` with a NaN delta. SQLite stores NaN as NULL, which violates `users_profile.cash_balance NOT NULL`, and `sqlite3.IntegrityError` escapes the route because it only catches `TradeError`. The surrounding `with conn:` rolls back, so balances are not corrupted.
- Files: `backend/app/portfolio/service.py` (`execute_trade`), `backend/app/portfolio/routes.py` (`trade`), `backend/app/portfolio/routes.py` `TradeRequest`
- Trigger: `curl -X POST /api/portfolio/trade -d '{"ticker":"AAPL","quantity":NaN,"side":"buy"}'` with a valid body otherwise. Reproduced with a direct call to `execute_trade` using `quantity=float('nan')`: `sqlite3.IntegrityError: NOT NULL constraint failed: users_profile.cash_balance`.
- Workaround: None needed for normal use. The frontend `Number("")` produces `NaN`, which `JSON.stringify` turns into `null`, so the UI path returns 422 rather than 500.
- Fix approach: In `execute_trade`, raise `TradeError` when `not math.isfinite(quantity)`. Add a test next to `backend/tests/portfolio/test_service.py`.

**Chat history disappears on page reload:**
- Symptoms: Every chat turn is saved to `chat_messages`, but no endpoint returns the history. `useTerminal` keeps messages in React state only, so a reload shows an empty panel.
- Files: `backend/app/chat/history.py` (`load_history` is only used for LLM context), `backend/app/chat/router.py` (no GET route), `frontend/hooks/useTerminal.ts` (`messages` state)
- Trigger: Send a chat message, reload the page.
- Workaround: None.
- Spec gap: PLAN §10 describes a "scrolling conversation history". PLAN §8 defines no history endpoint, so the spec does not cover this. Either add `GET /api/chat/history` to the spec and code, or document that history is session-only.

**Removing a ticker or adding one does not refresh portfolio state:**
- Symptoms: `addTicker` and `removeTicker` in `frontend/hooks/useTerminal.ts` update only the watchlist list. Removal errors are swallowed in `frontend/components/Terminal.tsx` (`.catch(() => {})`), so a failed removal shows no message.
- Files: `frontend/hooks/useTerminal.ts`, `frontend/components/Terminal.tsx`
- Trigger: Remove a ticker that is held, or have the request fail.
- Workaround: Reload the page.

## Security-Adjacent Input Handling

**No input size limits on chat or trade requests:**
- Risk: `ChatRequest.message` (`backend/app/chat/schema.py`) has no `max_length`. Every chat turn sends the full portfolio JSON, the last 20 messages, and the new text to OpenAI, so a very long message increases cost with no bound. `TradeRequest.quantity` has no upper bound beyond the cash check.
- Files: `backend/app/chat/schema.py`, `backend/app/portfolio/routes.py`
- Current mitigation: Only the local user can send requests (no auth, but single-user localhost per PLAN §3).
- Recommendations: Add `Field(max_length=2000)` to `ChatRequest.message`. Consider a sanity cap on quantity.

**No LLM timeout or retry bound:**
- Risk: `litellm.acompletion` in `backend/app/chat/llm.py` is called with no `timeout`. A hung provider connection keeps the `/api/chat` request open indefinitely, and the UI shows "FinAlly is thinking..." with no cancel control (`frontend/components/ChatPanel.tsx`). The chat input is also disabled while `loading` is true.
- Files: `backend/app/chat/llm.py`, `frontend/components/ChatPanel.tsx`
- Current mitigation: The exception path returns 502 on errors, but not on slow responses.
- Fix approach: Pass an explicit `timeout` (for example 30 seconds) to `litellm.acompletion`, and handle timeouts as 502.

**Partial chat execution is not atomic:**
- Risk: `execute_actions` in `backend/app/chat/execute.py` runs each watchlist change and each trade in its own transaction. `save_message` for the user and assistant messages runs after execution. If a database error occurs after some trades have executed, the trades stay in place but the chat record may be missing or incomplete.
- Files: `backend/app/chat/execute.py`, `backend/app/chat/router.py`
- Current mitigation: Each trade is atomic. Failed trades are reported in `actions`.
- Recommendations: Low priority for a single-user app. If needed, save the user message before execution and wrap the whole turn in one transaction.

## Performance Bottlenecks

**Full terminal re-render on every SSE tick:**
- Problem: `usePriceStream` calls `setState` for each SSE message, about twice per second. `Terminal` (`frontend/components/Terminal.tsx`) re-renders every panel on each update.
- Files: `frontend/hooks/usePriceStream.ts`, `frontend/components/Terminal.tsx`, `frontend/components/Watchlist.tsx`, `frontend/components/WatchlistRow.tsx`
- Cause: `pnlPoints` is rebuilt on every render, and `stream.history[selected]` is a new array after each `appendHistory` call. `LineChart` depends on `[points, color]`, so every tick calls `setData` and `fitContent()`.
- Improvement path: Memoize `pnlPoints` with `useMemo` keyed on `t.snapshots`. Move price state into per-row subscriptions or a store so only changed rows render. Call `fitContent()` only when the ticker changes, not on every data update.

**Main chart resets zoom and pan on every tick:**
- Problem: `LineChart` calls `timeScale().fitContent()` each time `points` changes (`frontend/components/LineChart.tsx`), which happens about twice per second. A user cannot zoom or pan the main chart.
- Files: `frontend/components/LineChart.tsx`
- Cause: The effect runs on every new `points` array identity (see the item above).
- Improvement path: Fit content only on first data or when `color`/ticker changes. Use `series.update()` for the newest point instead of `setData` for the whole series.

**Client history is never pruned:**
- Problem: `appendHistory` in `frontend/hooks/usePriceStream.ts` keeps each ticker's points (capped at 600) even after the ticker is removed from the watchlist. Each tick copies every ticker's array.
- Files: `frontend/hooks/usePriceStream.ts`
- Cause: No pruning of keys that are absent from the latest `prices` map.
- Improvement path: Drop history and session-start entries for tickers absent from the latest message.

**Full portfolio snapshot per SSE frame:**
- Problem: `backend/app/market/stream.py` sends every tracked ticker's full JSON on each version change. The simulator bumps the version every 0.5 s, so the payload is sent that often regardless of how many tickers changed.
- Files: `backend/app/market/stream.py`, `backend/app/market/cache.py`
- Cause: The version counter is global, not per ticker.
- Improvement path: Acceptable at 10 tickers. Send only changed tickers if the watchlist grows.

**Blocking SQLite and simulator work on the event loop:**
- Problem: Several handlers are `async def` but call synchronous SQLite code. `trade` in `backend/app/portfolio/routes.py` calls `execute_trade` directly, `add`/`remove` in `backend/app/watchlist/routes.py` do the same through `add_ticker` and `remove_ticker`, and `chat` in `backend/app/chat/router.py` builds context synchronously. `snapshot_loop` in `backend/app/main.py` also writes on the loop. Each call is short, but they run on the same thread as the SSE generator and the simulator.
- Files: `backend/app/portfolio/routes.py`, `backend/app/watchlist/routes.py`, `backend/app/chat/router.py`, `backend/app/main.py`
- Cause: SQLite calls are synchronous and are not moved to a thread.
- Improvement path: Make the SQLite-using handlers plain `def` (FastAPI runs them in a thread pool), or wrap blocking calls in `asyncio.to_thread`. Keep the change small.

**Watchlist size is unbounded:**
- Problem: No maximum on watchlist or tracked ticker count. `GBMSimulator._rebuild_cholesky` is O(n²) per add or remove and runs on the event loop. The Massive poller sends all tickers in one snapshot request, which grows with the list and is subject to the free-tier rate limit.
- Files: `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`, `backend/app/watchlist/service.py`
- Cause: No limit in `add_ticker`.
- Improvement path: Cap the watchlist at a documented size (for example 50), and reject additions beyond it with a 400.

## Market Data Fragility

**Massive add-ticker poll shares the global failure backoff:**
- Issue: `MassiveDataSource.add_ticker` calls `_poll_once(only=[ticker])`. A failure in that call increments `_consecutive_failures`, which the regular poll loop also uses in `_next_delay`. One bad add therefore slows polling for every ticker, up to the 120-second cap.
- Files: `backend/app/market/massive_client.py` (`add_ticker`, `_poll_once`, `_next_delay`)
- Trigger: Add a ticker while the API is rate-limiting or returns a 5xx error.
- Impact: The new ticker has no price, so a buy fails with "no price available" (PLAN §8). Global polling also slows.
- Fix approach: Track failures per call, or let the add path skip the failure counter. Retry the first quote on the next regular poll. Test with `backend/tests/market/test_massive.py`.

**Free-tier budget consumed by ticker adds:**
- Issue: Each add costs one extra call. On the free tier (5 calls/minute), a burst of adds delays the regular 15-second poll.
- Files: `backend/app/market/massive_client.py`, `backend/app/market/factory.py`
- Impact: Documented in `.env.example`, but nothing enforces it.
- Fix approach: Batch pending adds into the next poll on the free tier, or document the budget in `README.md`.

**Simulator tracks an unknown symbol at a random seed price:**
- Issue: `backend/app/market/simulator.py` seeds unknown tickers with `UNKNOWN_SEED_RANGE` ($50-$300). This matches PLAN §6, but a user can "buy" a symbol that has no real price, and the price is arbitrary.
- Files: `backend/app/market/simulator.py`, `backend/app/market/seed_prices.py`
- Impact: Expected in simulator mode. Worth noting for the user.

## Fragile Areas

**Watchlist and position tracking are coupled through `sync_tracked_tickers`:**
- Files: `backend/app/db/tickers.py`, `backend/app/portfolio/routes.py`, `backend/app/watchlist/service.py`, `backend/app/chat/execute.py`
- Why fragile: Every write path must call `sync_tracked_tickers` after changing watchlist or positions. `execute_actions` calls it only when `trades` is non-empty, which is correct today because watchlist changes already sync, but a future change that alters positions without trades would silently skip the sync.
- Safe modification: Keep `sync_tracked_tickers` at the end of every route or service that mutates either table. Cover new paths with a test that asserts `source.get_tickers()` after the call.
- Test coverage: `backend/tests/db/test_db.py` covers the reconciliation function. Chat paths are covered by `backend/tests/chat/test_router.py`.

**Shared mutable state in the market data layer:**
- Files: `backend/app/market/cache.py`, `backend/app/market/simulator.py`, `backend/app/market/massive_client.py`
- Why fragile: `PriceCache` is protected by a lock, but `GBMSimulator` is not thread-safe, and `MassiveDataSource._tickers` is read in a worker thread via `_poll_once`. The current design keeps simulator writes on the loop and only the Massive fetch in a thread, so there is no race today. Moving the simulator to threads would break it.
- Safe modification: Keep all `GBMSimulator` calls on the event loop. Reads of `_tickers` happen on the loop before `to_thread` is called.
- Test coverage: Unit tests exist for both sources. There is no concurrency test.

**Frontend SSE parsing is unguarded:**
- Files: `frontend/hooks/usePriceStream.ts`
- Why fragile: `JSON.parse(event.data)` is not wrapped in a try block. A malformed frame throws inside `onmessage` and is reported as an uncaught error, and the status is not updated.
- Safe modification: Wrap the parse and ignore bad frames.
- Test coverage: `frontend/components/components.test.tsx` does not test `usePriceStream`.

**Dependence on float equality in the flash effect:**
- Files: `frontend/components/WatchlistRow.tsx` (`useFlash`)
- Why fragile: `useFlash` compares the previous and current price with `===`. Values are rounded to cents on the backend (`PriceCache.update`), so this is safe today.
- Safe modification: Keep rounding in `PriceCache.update`.

## Error Handling Gaps

**Silent failures in the frontend:**
- Files: `frontend/hooks/useTerminal.ts` (`refresh().catch(() => {})`, history interval `.catch(() => {})`), `frontend/components/Terminal.tsx` (`removeTicker(...).catch(() => {})`)
- Problem: Initial load and periodic refresh failures are swallowed, so the page can show stale or empty data with no indication.
- Fix approach: Surface a small status or error line in the header or the relevant panel.

**Error detail is shown only for string details:**
- Files: `frontend/lib/api.ts` (`request`)
- Problem: FastAPI validation errors (422) return `detail` as a list, so the UI shows `Request failed (422)`.
- Fix approach: Format list details into a readable message.

**No handling for a failed snapshot write other than logging:**
- Files: `backend/app/main.py` (`snapshot_loop`)
- Problem: A failed snapshot is logged and skipped. Gaps in the P&L chart are silent.
- Fix approach: Acceptable. The next snapshot 30 seconds later recovers.

## Operations and Deployment

**Container runs as root with test code in the image:**
- Files: `Dockerfile`, `.dockerignore`
- Problem: The image has no `USER` directive, so the server process runs as root. `backend/tests/` and `backend/market_data_demo.py` are copied because `.dockerignore` excludes only root-level `test/`, not `backend/tests`.
- Fix approach: Add a non-root user in the Python stage. Exclude `backend/tests` and `backend/market_data_demo.py` in `.dockerignore`.

**Stale image after code changes:**
- Files: `scripts/start_mac.sh`, `scripts/start_windows.ps1`
- Problem: The script rebuilds only when the image is missing or `--build`/`-Build` is passed. Developers who edit code and run the start script without the flag run the old image.
- Fix approach: Document that `--build` is required after code changes, or always run `docker build` (cached builds are fast).

**Health check uses a Python interpreter in the image:**
- Files: `Dockerfile` (HEALTHCHECK), `test/docker-compose.test.yml`
- Problem: The check runs `python -c ...` outside the uv environment. It works today because `python` is on the path in `python:3.13-slim`.
- Fix approach: Acceptable. Keep it in mind if the base image changes.

**Unbounded tables:**
- Files: `backend/db/schema.sql` (`portfolio_snapshots`, `chat_messages`, `trades`)
- Problem: No retention on any table. PLAN §7 accepts snapshot growth (about 2,900 rows per day). `chat_messages` and `trades` have no stated limit.
- Fix approach: Acceptable for the demo. `GET /api/portfolio/history` already caps reads at 1,000 rows (`backend/app/portfolio/service.py`).

## Scaling Limits

**Single SQLite file with one connection per request:**
- Current capacity: One user, one process, one container (PLAN §3).
- Limit: Concurrent writes are serialized by SQLite. The file is not in WAL mode (`backend/app/db/connection.py` does not set `journal_mode`).
- Scaling path: Enable WAL if write concurrency grows. PLAN §3 already defers multi-user support.

**In-memory price cache is single-process:**
- Current capacity: One uvicorn worker. `backend/app/main.py` creates the cache at import time.
- Limit: Running more than one worker would give each worker its own cache and simulator, so prices would differ between requests.
- Scaling path: Keep one worker. The Dockerfile `CMD` already runs a single process.

## Spec Gaps

Compared against `planning/PLAN.md`:

- **Chat history retrieval (§10):** Persisted (§7) but not retrievable (§8 defines no route). See Known Bugs.
- **Concurrency and error semantics (§8):** Implemented as specified. `DELETE /api/watchlist/{ticker}` returns 400 for malformed input rather than 404, which the spec does not address.
- **Massive immediate-buy scenario (§6, §9):** Partly addressed. `add_ticker` polls once immediately, but a failed poll leaves the ticker unpriced with no retry until the next interval. See Market Data Fragility.
- **OpenAI skill (§9):** Referenced guidance file is missing. See Tech Debt.
- **Deploy stretch goal (§11):** `deploy/` Terraform is absent. Optional in the spec.
- **E2E scenarios (§12):** All listed scenarios have Playwright tests in `test/tests/`. The suite is not run in CI (see Tech Debt).
- **Unit test scope (§12):** Backend tests cover market data, portfolio, LLM parsing, and routes. Frontend tests cover header, watchlist row flash, positions, heatmap colors, and chat rendering. Not covered: `usePriceStream` parsing and reconnection, and `useTerminal` error paths.

## Test Coverage Gaps

**Trade input edge cases:**
- What's not tested: Non-finite quantities (`NaN`, `inf`) in `execute_trade`.
- Files: `backend/tests/portfolio/test_service.py`, `backend/app/portfolio/service.py`
- Risk: The 500 response in Known Bugs goes unnoticed.
- Priority: Medium

**Chat partial-failure path:**
- What's not tested: A database error midway through `execute_actions` or during `save_message`.
- Files: `backend/tests/chat/test_router.py`, `backend/app/chat/execute.py`
- Risk: Trades execute without a matching chat record.
- Priority: Low

**Massive add failure and backoff:**
- What's not tested: A failed `add_ticker` poll affecting the regular poll interval.
- Files: `backend/tests/market/test_massive.py`, `backend/app/market/massive_client.py`
- Risk: Global polling slows after a single failed add.
- Priority: Medium

**Frontend SSE and reconnection:**
- What's not tested in unit tests: `usePriceStream` message parsing, malformed frames, and `status` transitions. The Playwright reconnection test (`test/tests/03-ui.spec.ts`) covers the happy reconnect only.
- Files: `frontend/hooks/usePriceStream.ts`
- Risk: Silent state issues on malformed or unexpected frames.
- Priority: Medium

**Frontend chart behavior under live updates:**
- What's not tested: Chart zoom and pan persistence across ticks.
- Files: `frontend/components/LineChart.tsx`
- Risk: The fit-content reset (see Performance) goes unnoticed.
- Priority: Low

**Frontend build from a clean checkout:**
- What's not tested: Any build from a fresh clone. Concern 1 would have been caught by a CI job that runs `npm ci && npm run build` from a clean checkout.
- Files: `.gitignore`, `frontend/`
- Risk: The Docker image cannot be built from the repository.
- Priority: High

---

*Concerns audit: 2026-11-04*
