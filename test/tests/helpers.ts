import { APIRequestContext, expect } from "@playwright/test";

export const DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"];

/** Fetch GET /api/portfolio and return the parsed body. */
export async function getPortfolio(request: APIRequestContext) {
  const res = await request.get("/api/portfolio");
  expect(res.status()).toBe(200);
  return res.json();
}

/** Poll the watchlist until the ticker has a cached price, then return it. */
export async function waitForPrice(request: APIRequestContext, ticker: string): Promise<number> {
  let price: number | null = null;
  await expect
    .poll(async () => {
      const body = await (await request.get("/api/watchlist")).json();
      price = body.tickers.find((t: { ticker: string }) => t.ticker === ticker)?.price ?? null;
      return price;
    })
    .not.toBeNull();
  return price as unknown as number;
}

/** Return the held quantity of a ticker (0 if no position). */
export async function heldQuantity(request: APIRequestContext, ticker: string): Promise<number> {
  const portfolio = await getPortfolio(request);
  return portfolio.positions.find((p: { ticker: string }) => p.ticker === ticker)?.quantity ?? 0;
}

/** Remove a ticker from the watchlist if present (test cleanup). */
export async function removeIfWatched(request: APIRequestContext, ticker: string) {
  const res = await request.delete(`/api/watchlist/${ticker}`);
  expect([204, 404]).toContain(res.status());
}
