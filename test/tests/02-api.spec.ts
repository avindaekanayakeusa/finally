import { expect, test } from "@playwright/test";
import { DEFAULT_TICKERS, getPortfolio, heldQuantity, removeIfWatched, waitForPrice } from "./helpers";

const ISO_UTC = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$/;

test.describe("API contract", () => {
  test("health returns ok", async ({ request }) => {
    const res = await request.get("/api/health");
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({ status: "ok" });
  });

  test("portfolio has the documented shape", async ({ request }) => {
    const p = await getPortfolio(request);
    for (const key of ["cash_balance", "total_value", "positions_value", "unrealized_pnl"]) {
      expect(typeof p[key]).toBe("number");
    }
    expect(Array.isArray(p.positions)).toBe(true);
    expect(p.total_value).toBeCloseTo(p.cash_balance + p.positions_value, 6);
  });

  test("watchlist lists default tickers with prices", async ({ request }) => {
    await waitForPrice(request, "AAPL");
    const body = await (await request.get("/api/watchlist")).json();
    const tickers = body.tickers.map((t: { ticker: string }) => t.ticker);
    for (const t of DEFAULT_TICKERS) expect(tickers).toContain(t);
    const aapl = body.tickers.find((t: { ticker: string }) => t.ticker === "AAPL");
    expect(Object.keys(aapl).sort()).toEqual(["added_at", "direction", "previous_price", "price", "ticker"]);
    expect(typeof aapl.price).toBe("number");
    expect(["up", "down", "flat"]).toContain(aapl.direction);
    expect(aapl.added_at).toMatch(ISO_UTC);
  });

  test("watchlist add, duplicate, delete, delete missing", async ({ request }) => {
    await removeIfWatched(request, "PYPL");

    const add = await request.post("/api/watchlist", { data: { ticker: "pypl" } });
    expect(add.status()).toBe(201);
    const entry = await add.json();
    expect(entry.ticker).toBe("PYPL");
    expect(entry.added_at).toMatch(ISO_UTC);

    const dup = await request.post("/api/watchlist", { data: { ticker: "PYPL" } });
    expect(dup.status()).toBe(400);
    expect(typeof (await dup.json()).detail).toBe("string");

    const del = await request.delete("/api/watchlist/PYPL");
    expect(del.status()).toBe(204);
    expect(await del.text()).toBe("");

    const missing = await request.delete("/api/watchlist/PYPL");
    expect(missing.status()).toBe(404);
    expect(typeof (await missing.json()).detail).toBe("string");
  });

  test("invalid ticker format is rejected with 400", async ({ request }) => {
    for (const ticker of ["123", "TOOLONG", "AB-C", ""]) {
      const res = await request.post("/api/watchlist", { data: { ticker } });
      expect(res.status(), `ticker "${ticker}"`).toBe(400);
    }
    const trade = await request.post("/api/portfolio/trade", { data: { ticker: "12", quantity: 1, side: "buy" } });
    expect(trade.status()).toBe(400);
  });

  test("buy then sell returns trade and portfolio", async ({ request }) => {
    await waitForPrice(request, "MSFT");
    const before = await heldQuantity(request, "MSFT");

    const buy = await request.post("/api/portfolio/trade", { data: { ticker: "MSFT", quantity: 2, side: "buy" } });
    expect(buy.status()).toBe(200);
    const body = await buy.json();
    expect(body.trade).toMatchObject({ ticker: "MSFT", side: "buy", quantity: 2 });
    expect(typeof body.trade.id).toBe("string");
    expect(typeof body.trade.price).toBe("number");
    expect(body.trade.executed_at).toMatch(ISO_UTC);
    const pos = body.portfolio.positions.find((p: { ticker: string }) => p.ticker === "MSFT");
    expect(pos.quantity).toBeCloseTo(before + 2, 9);
    for (const key of ["avg_cost", "current_price", "market_value", "unrealized_pnl", "pnl_percent"]) {
      expect(typeof pos[key]).toBe("number");
    }

    const sell = await request.post("/api/portfolio/trade", { data: { ticker: "MSFT", quantity: 2, side: "sell" } });
    expect(sell.status()).toBe(200);
    expect(await heldQuantity(request, "MSFT")).toBeCloseTo(before, 9);
  });

  test("fractional buy and full sell removes the position", async ({ request }) => {
    await waitForPrice(request, "JPM");
    expect(await heldQuantity(request, "JPM")).toBe(0);
    const buy = await request.post("/api/portfolio/trade", { data: { ticker: "JPM", quantity: 0.5, side: "buy" } });
    expect(buy.status()).toBe(200);
    const sell = await request.post("/api/portfolio/trade", { data: { ticker: "JPM", quantity: 0.5, side: "sell" } });
    expect(sell.status()).toBe(200);
    expect(await heldQuantity(request, "JPM")).toBe(0);
  });

  test("insufficient cash is rejected with 400", async ({ request }) => {
    await waitForPrice(request, "AAPL");
    const res = await request.post("/api/portfolio/trade", { data: { ticker: "AAPL", quantity: 1_000_000, side: "buy" } });
    expect(res.status()).toBe(400);
    expect((await res.json()).detail).toMatch(/insufficient cash/i);
  });

  test("selling more than held is rejected with 400", async ({ request }) => {
    await waitForPrice(request, "TSLA");
    const held = await heldQuantity(request, "TSLA");
    const res = await request.post("/api/portfolio/trade", { data: { ticker: "TSLA", quantity: held + 1, side: "sell" } });
    expect(res.status()).toBe(400);
    expect(typeof (await res.json()).detail).toBe("string");
  });

  test("non-positive quantity is rejected with 400", async ({ request }) => {
    for (const quantity of [0, -1]) {
      const res = await request.post("/api/portfolio/trade", { data: { ticker: "AAPL", quantity, side: "buy" } });
      expect(res.status(), `quantity ${quantity}`).toBe(400);
    }
  });

  test("buying an untracked ticker is rejected with 400", async ({ request }) => {
    await removeIfWatched(request, "ZZZZ");
    const res = await request.post("/api/portfolio/trade", { data: { ticker: "ZZZZ", quantity: 1, side: "buy" } });
    expect(res.status()).toBe(400);
  });

  test("malformed trade body is rejected with 422", async ({ request }) => {
    const res = await request.post("/api/portfolio/trade", { data: { ticker: "AAPL", side: "hold" } });
    expect(res.status()).toBe(422);
  });

  test("portfolio history returns snapshots oldest first", async ({ request }) => {
    const body = await (await request.get("/api/portfolio/history")).json();
    expect(body.snapshots.length).toBeGreaterThan(0);
    const times = body.snapshots.map((s: { recorded_at: string }) => s.recorded_at);
    expect([...times].sort()).toEqual(times);
    expect(typeof body.snapshots[0].total_value).toBe("number");
    expect(body.snapshots[0].recorded_at).toMatch(ISO_UTC);
  });

  test("mock chat with no action keyword returns empty actions", async ({ request }) => {
    const res = await request.post("/api/chat", { data: { message: "hello there" } });
    expect(res.status()).toBe(200);
    expect(await res.json()).toEqual({
      message: "Mock: I am FinAlly, your AI trading assistant.",
      actions: { trades: [], watchlist_changes: [] },
    });
  });

  test("mock chat buy and sell execute trades", async ({ request }) => {
    await waitForPrice(request, "AAPL");
    const before = await heldQuantity(request, "AAPL");
    const res = await request.post("/api/chat", { data: { message: "Please BUY something" } });
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.message).toBe("Mock: buying 1 AAPL.");
    expect(body.actions.trades).toHaveLength(1);
    expect(body.actions.trades[0]).toMatchObject({ ticker: "AAPL", side: "buy", quantity: 1, status: "executed", error: null });
    expect(await heldQuantity(request, "AAPL")).toBeCloseTo(before + 1, 9);

    const sell = await request.post("/api/chat", { data: { message: "sell it" } });
    expect((await sell.json()).actions.trades[0].status).toBe("executed");
    expect(await heldQuantity(request, "AAPL")).toBeCloseTo(before, 9);
  });

  test("mock chat watch adds PYPL", async ({ request }) => {
    await removeIfWatched(request, "PYPL");
    const res = await request.post("/api/chat", { data: { message: "watch paypal" } });
    const body = await res.json();
    expect(body.actions.watchlist_changes[0]).toMatchObject({ ticker: "PYPL", action: "add", status: "executed", error: null });
    await removeIfWatched(request, "PYPL");
  });

  test("SSE stream sends retry then a price event", async ({ page }) => {
    await page.goto("/api/health");
    const result = await page.evaluate(async () => {
      const res = await fetch("/api/stream/prices");
      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let text = "";
      while (!/data: .*\n/.test(text)) {
        const { value } = await reader.read();
        text += decoder.decode(value);
      }
      await reader.cancel();
      return { contentType: res.headers.get("content-type"), text };
    });
    expect(result.contentType).toContain("text/event-stream");
    expect(result.text.startsWith("retry: 1000")).toBe(true);
    const data = JSON.parse(result.text.match(/data: (.*)\n/)![1]);
    expect(data.AAPL).toMatchObject({ ticker: "AAPL" });
    for (const key of ["price", "previous_price", "timestamp", "change", "change_percent"]) {
      expect(typeof data.AAPL[key]).toBe("number");
    }
    expect(["up", "down", "flat"]).toContain(data.AAPL.direction);
  });
});
