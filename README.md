# FinAlly — AI Trading Workstation

An AI-powered trading workstation: live market data streaming, a simulated portfolio, and an LLM chat assistant that can analyze positions and execute trades in natural language. Think Bloomberg terminal with an AI copilot.

Built entirely by coding agents as the capstone project for an agentic AI coding course. Agents coordinate through the docs in `planning/`.

## Status

| Component | Status |
|---|---|
| Market data (GBM simulator, Massive API client, price cache, SSE stream) | Done |
| Backend API (portfolio, trades, watchlist, chat, database) | Planned |
| Frontend (Next.js) | Planned |
| Docker image, start/stop scripts, E2E tests | Planned |

The full specification is in [planning/PLAN.md](planning/PLAN.md).

## Features (target)

- Live price streaming over SSE with green/red flash animations and sparklines
- Simulated portfolio: $10k virtual cash, market orders, instant fills
- Portfolio heatmap, P&L chart and positions table
- AI chat assistant that analyzes holdings and auto-executes trades
- Watchlist managed manually or through the AI
- Dark, data-dense terminal aesthetic

## Architecture

One Docker container on port 8000:

- **Frontend**: Next.js static export, TypeScript, Tailwind CSS
- **Backend**: FastAPI (Python, managed with `uv`), SSE streaming
- **Database**: SQLite at `db/finally.db`, created and seeded at startup
- **AI**: LiteLLM to OpenAI `gpt-5-mini` with structured outputs
- **Market data**: built-in GBM simulator by default, or the Massive (Polygon.io) API

## Try What Exists Today

Requires [uv](https://docs.astral.sh/uv/).

```bash
cd backend
uv sync --extra dev
uv run market_data_demo.py   # live terminal dashboard of simulated prices
uv run pytest                # market data unit tests
```

## Environment Variables

Set in `.env` at the project root.

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | For live chat | Not needed when `LLM_MOCK=true` |
| `MASSIVE_API_KEY` | No | Real market data; omit to use the simulator |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses (testing, no key needed) |

## Running with Docker (once built)

```bash
docker build -t finally .
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
# open http://localhost:8000
```

## Project Structure

```
finally/
├── backend/     # FastAPI uv project (market data done; see backend/README.md)
├── frontend/    # Next.js app (planned)
├── planning/    # PLAN.md spec, reviews, archived design docs
├── test/        # Playwright E2E tests (planned)
├── scripts/     # Docker start/stop helpers (planned)
├── db/          # SQLite volume mount at runtime
└── .claude/     # Agent tooling: skills, subagents, commands, hooks
```

## Agent Tooling

- `.claude/skills/openai-llm/` explains how to call OpenAI through LiteLLM
- `.claude/agents/change-reviewer.md` is a subagent that has Codex review uncommitted changes
- `.claude/settings.json` has a Stop hook that runs a Codex review into `planning/REVIEW.md` after each Claude response

## License

See [LICENSE](LICENSE).
