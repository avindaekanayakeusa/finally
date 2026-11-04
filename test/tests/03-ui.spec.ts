import { expect, Page, test } from "@playwright/test";
import { getPortfolio, heldQuantity, removeIfWatched, waitForPrice } from "./helpers";

/** Parse displayed money like "$9,809.50" into a number. */
function parseMoney(text: string | null): number {
  return Number((text ?? "").replace(/[^0-9.-]/g, ""));
}

async function displayedCash(page: Page): Promise<number> {
  return parseMoney(await page.getByTestId("cash-balance").textContent());
}

async function trade(page: Page, ticker: string, quantity: string, side: "buy" | "sell") {
  await page.getByTestId("trade-ticker").fill(ticker);
  await page.getByTestId("trade-quantity").fill(quantity);
  await page.getByTestId(`trade-${side}`).click();
}

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
});

test("add and remove a ticker from the watchlist", async ({ page, request }) => {
  await removeIfWatched(request, "PYPL");
  await page.reload();

  await page.getByTestId("watchlist-input").fill("pypl");
  await page.getByTestId("watchlist-add").click();
  await expect(page.getByTestId("watchlist-row-PYPL")).toBeVisible();
  await expect(page.getByTestId("price-PYPL")).toHaveText(/\d+\.\d{2}/);

  await page.getByTestId("remove-PYPL").click();
  await expect(page.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
});

test("clicking a ticker shows the main chart", async ({ page }) => {
  await page.getByTestId("watchlist-row-NVDA").click();
  await expect(page.getByTestId("main-chart")).toBeVisible();
  await expect(page.getByText("NVDA - Price")).toBeVisible();
  await expect(page.getByTestId("main-chart").locator("canvas").first()).toBeVisible();
  await expect.poll(async () => Number(await page.getByTestId("main-chart").getAttribute("data-points"))).toBeGreaterThan(1);
});

test("buy shares: cash decreases and position appears", async ({ page, request }) => {
  await waitForPrice(request, "GOOGL");
  const before = await getPortfolio(request);
  await expect.poll(() => displayedCash(page)).toBeCloseTo(before.cash_balance, 2);

  await trade(page, "GOOGL", "3", "buy");

  await expect(page.getByTestId("position-row-GOOGL")).toBeVisible();
  await expect.poll(() => displayedCash(page)).toBeLessThan(before.cash_balance);
  expect(await heldQuantity(request, "GOOGL")).toBeCloseTo(3, 9);
});

test("sell shares: cash increases, position updates then disappears", async ({ page, request }) => {
  expect(await heldQuantity(request, "GOOGL")).toBeCloseTo(3, 9);
  const before = await getPortfolio(request);

  await trade(page, "GOOGL", "1", "sell");
  await expect.poll(() => displayedCash(page)).toBeGreaterThan(before.cash_balance);
  await expect.poll(() => heldQuantity(request, "GOOGL")).toBeCloseTo(2, 9);
  await expect(page.getByTestId("position-row-GOOGL")).toBeVisible();

  await trade(page, "GOOGL", "2", "sell");
  await expect(page.getByTestId("position-row-GOOGL")).toHaveCount(0);
});

test("failed trade shows an error", async ({ page }) => {
  await trade(page, "AAPL", "1000000", "buy");
  await expect(page.getByTestId("trade-message")).toContainText(/insufficient cash/i);
});

test("heatmap and P&L chart render with a position", async ({ page, request }) => {
  await waitForPrice(request, "AMZN");
  await trade(page, "AMZN", "2", "buy");

  await expect(page.getByTestId("heatmap")).toBeVisible();
  await expect(page.getByTestId("heatmap-cell-AMZN")).toBeVisible();
  await expect(page.getByTestId("heatmap-cell-AMZN")).toHaveAttribute("data-pnl", /^(profit|loss)$/);
  await expect(page.getByTestId("pnl-chart")).toBeVisible();
  await expect(page.getByTestId("pnl-chart").locator("canvas").first()).toBeVisible();
  await expect.poll(async () => Number(await page.getByTestId("pnl-chart").getAttribute("data-points"))).toBeGreaterThan(0);

  await trade(page, "AMZN", "2", "sell");
  await expect(page.getByTestId("heatmap-cell-AMZN")).toHaveCount(0);
});

test("AI chat (mocked) shows response and inline trade confirmation", async ({ page, request }) => {
  await waitForPrice(request, "AAPL");
  const before = await heldQuantity(request, "AAPL");

  await page.getByTestId("chat-input").fill("buy some apple");
  await page.getByTestId("chat-send").click();

  await expect(page.getByTestId("chat-message-user").last()).toContainText("buy some apple");
  await expect(page.getByTestId("chat-message-assistant").last()).toContainText("Mock: buying 1 AAPL.");
  await expect(page.getByTestId("chat-action").last()).toContainText("AAPL");
  await expect(page.getByTestId("chat-action").last()).toHaveAttribute("data-status", "executed");
  await expect(page.getByTestId("chat-loading")).toHaveCount(0);
  await expect(page.getByTestId("position-row-AAPL")).toBeVisible();
  expect(await heldQuantity(request, "AAPL")).toBeCloseTo(before + 1, 9);
});

test("SSE reconnects after the server drops the stream", async ({ page }) => {
  const status = page.getByTestId("connection-status");
  // While routed, every stream request gets a valid SSE response that closes at once,
  // so EventSource errors and keeps retrying, as if the server kept dropping it.
  let attempts = 0;
  await page.route("**/api/stream/prices", (route) => {
    attempts += 1;
    return route.fulfill({ status: 200, contentType: "text/event-stream", body: "retry: 300\n\n" });
  });
  await page.reload();
  await expect.poll(() => attempts).toBeGreaterThanOrEqual(2);
  await expect(status).toHaveAttribute("data-status", "reconnecting");

  await page.unroute("**/api/stream/prices");
  await expect(status).toHaveAttribute("data-status", "connected");
  const price = page.getByTestId("price-AAPL");
  await expect(price).toHaveText(/\d+\.\d{2}/);
  const first = await price.textContent();
  await expect(price).not.toHaveText(first!);
});

