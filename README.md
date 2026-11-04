# FinAlly — AI Trading Workstation

An AI-powered trading workstation: live market data streaming, a simulated portfolio, and an LLM chat assistant that can analyze positions and execute trades in natural language. Think Bloomberg terminal with an AI copilot.

Built entirely by coding agents as the capstone project for an agentic AI coding course. Agents coordinate through the docs in `planning/`. The full specification is in [planning/PLAN.md](planning/PLAN.md).

## Quick Start

Requires Docker.

```bash
cp .env.example .env        # add OPENAI_API_KEY, or set LLM_MOCK=true
./scripts/start_mac.sh      # macOS/Linux (add --build to rebuild)
./scripts/stop_mac.sh
```

```powershell
.\scripts\start_windows.ps1   # Windows (add -Build to rebuild, -NoBrowser to skip opening)
.\scripts\stop_windows.ps1
```

Open http://localhost:8000. Data persists in the `finally-data` Docker volume.

Manual equivalent:

```bash
docker build -t finally .
docker run -d --name finally -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

## Features

- Live price streaming over SSE with green/red flash animations and sparklines
- Simulated portfolio: $10k virtual cash, market orders, instant fills
- Portfolio heatmap, P&L chart and positions table
- AI chat assistant that analyzes holdings and auto-executes trades
- Watchlist managed manually or through the AI

## Architecture

One Docker container on port 8000:

- **Frontend**: Next.js static export, TypeScript, Tailwind CSS
- **Backend**: FastAPI (Python, managed with `uv`), SSE streaming
- **Database**: SQLite at `db/finally.db`, created and seeded at startup
- **AI**: LiteLLM to OpenAI `gpt-5-mini` with structured outputs
- **Market data**: built-in GBM simulator by default, or the Massive (Polygon.io) API

## Environment Variables

Set in `.env` at the project root (see `.env.example`).

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | For live chat | Not needed when `LLM_MOCK=true` |
| `MASSIVE_API_KEY` | No | Real market data; omit to use the simulator |
| `MASSIVE_POLL_INTERVAL` | No | Massive poll interval in seconds (default 15) |
| `LLM_MOCK` | No | `true` for deterministic mock LLM responses (testing, no key needed) |

## Development

```bash
cd backend && uv sync --extra dev && uv run pytest
cd frontend && npm ci && npm run build
```

## Project Structure

```
finally/
├── backend/     # FastAPI uv project
├── frontend/    # Next.js app (static export)
├── planning/    # PLAN.md spec and agent docs
├── test/        # Playwright E2E tests
├── scripts/     # Docker start/stop helpers
└── db/          # SQLite volume mount at runtime
```

## License

See [LICENSE](LICENSE).
