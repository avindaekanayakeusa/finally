import { expect, test } from "@playwright/test";
import { DEFAULT_TICKERS } from "./helpers";

/** Runs first against a fresh database: defaults must be untouched. */
test("fresh start shows default watchlist, $10,000 cash and streaming prices", async ({ page }) => {
  await page.goto("/");

  for (const ticker of DEFAULT_TICKERS) {
    await expect(page.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
  }
  await expect(page.getByTestId("cash-balance")).toContainText("$10,000.00");
  await expect(page.getByTestId("total-value")).toContainText("$10,000.00");
  await expect(page.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");

  const price = page.getByTestId("price-AAPL");
  await expect(price).toHaveText(/\d+\.\d{2}/);
  const first = await price.textContent();
  await expect(price).not.toHaveText(first!);
});
