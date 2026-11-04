# FinAlly E2E tests

Playwright suite. Tests share one database and run serially; they expect a fresh DB (`01-fresh-start` asserts $10,000 cash).

## Docker (recommended)

From the project root:

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down
```

The app runs with `LLM_MOCK=true` and a tmpfs database, so every run starts fresh.

## Local

Start the app on port 8000 with `LLM_MOCK=true` and a fresh database, then:

```bash
cd test
npm install
npx playwright install chromium
npx playwright test            # BASE_URL defaults to http://localhost:8000
```
