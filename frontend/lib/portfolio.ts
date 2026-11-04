import type { ChartPoint, Portfolio, PriceMap } from "./types";

/** Reprice a portfolio with the latest streamed prices so totals update live. */
export function applyLivePrices(portfolio: Portfolio, prices: PriceMap): Portfolio {
  const positions = portfolio.positions.map((p) => {
    const current = prices[p.ticker]?.price ?? p.current_price;
    const marketValue = p.quantity * current;
    const cost = p.quantity * p.avg_cost;
    const pnl = marketValue - cost;
    return {
      ...p,
      current_price: current,
      market_value: marketValue,
      unrealized_pnl: pnl,
      pnl_percent: cost ? (pnl / cost) * 100 : 0,
    };
  });
  const positionsValue = positions.reduce((sum, p) => sum + p.market_value, 0);
  const unrealized = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
  return {
    cash_balance: portfolio.cash_balance,
    positions,
    positions_value: positionsValue,
    unrealized_pnl: unrealized,
    total_value: portfolio.cash_balance + positionsValue,
  };
}

/** Percent change from a session start price, in percent units. */
export function sessionChangePercent(start: number | undefined, current: number): number {
  return start ? ((current - start) / start) * 100 : 0;
}

/** Collapse points to one per whole second (last wins), ascending, for Lightweight Charts. */
export function toChartData(points: ChartPoint[]): ChartPoint[] {
  const bySecond = new Map<number, number>();
  for (const p of points) bySecond.set(Math.floor(p.time), p.value);
  return [...bySecond.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }));
}
