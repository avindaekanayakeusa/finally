import { describe, expect, it } from "vitest";
import { applyLivePrices, sessionChangePercent, toChartData } from "./portfolio";
import { treemap } from "./treemap";
import type { Portfolio, PriceUpdate } from "./types";

const portfolio: Portfolio = {
  cash_balance: 8000,
  total_value: 10000,
  positions_value: 2000,
  unrealized_pnl: 0,
  positions: [
    {
      ticker: "AAPL",
      quantity: 10,
      avg_cost: 200,
      current_price: 200,
      market_value: 2000,
      unrealized_pnl: 0,
      pnl_percent: 0,
    },
  ],
};

function tick(ticker: string, price: number): PriceUpdate {
  return {
    ticker,
    price,
    previous_price: price,
    timestamp: 0,
    change: 0,
    change_percent: 0,
    direction: "flat",
  };
}

describe("applyLivePrices", () => {
  it("reprices positions and totals from the stream", () => {
    const live = applyLivePrices(portfolio, { AAPL: tick("AAPL", 210) });
    expect(live.positions[0].market_value).toBe(2100);
    expect(live.positions[0].unrealized_pnl).toBe(100);
    expect(live.positions[0].pnl_percent).toBeCloseTo(5);
    expect(live.positions_value).toBe(2100);
    expect(live.total_value).toBe(10100);
  });

  it("keeps the server price when no tick is cached", () => {
    const live = applyLivePrices(portfolio, {});
    expect(live.total_value).toBe(10000);
  });

  it("handles a loss", () => {
    const live = applyLivePrices(portfolio, { AAPL: tick("AAPL", 180) });
    expect(live.unrealized_pnl).toBe(-200);
    expect(live.positions[0].pnl_percent).toBeCloseTo(-10);
  });
});

describe("sessionChangePercent", () => {
  it("computes percent vs the first price", () => {
    expect(sessionChangePercent(100, 102)).toBeCloseTo(2);
    expect(sessionChangePercent(undefined, 102)).toBe(0);
  });
});

describe("toChartData", () => {
  it("dedupes by whole second, last value wins, ascending", () => {
    const data = toChartData([
      { time: 2.4, value: 3 },
      { time: 1.1, value: 1 },
      { time: 1.6, value: 2 },
    ]);
    expect(data).toEqual([
      { time: 1, value: 2 },
      { time: 2, value: 3 },
    ]);
  });
});

describe("treemap", () => {
  it("fills the area with areas proportional to weight", () => {
    const rects = treemap([
      { id: "A", weight: 3 },
      { id: "B", weight: 1 },
    ]);
    const area = (id: string) => {
      const r = rects.find((x) => x.id === id)!;
      return r.w * r.h;
    };
    expect(area("A") + area("B")).toBeCloseTo(10000);
    expect(area("A") / area("B")).toBeCloseTo(3);
  });

  it("returns nothing for empty input", () => {
    expect(treemap([])).toEqual([]);
  });
});
