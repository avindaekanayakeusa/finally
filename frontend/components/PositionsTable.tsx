import { formatPercent, formatPrice, formatQty, formatUsd, signClass } from "@/lib/format";
import type { Position } from "@/lib/types";

const HEADERS = ["Ticker", "Qty", "Avg Cost", "Price", "Unrealized P&L", "%"];

/** Table of open positions with live P&L. */
export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <table data-testid="positions-table" className="w-full text-sm">
      <thead className="text-[11px] uppercase text-muted">
        <tr>
          {HEADERS.map((h, i) => (
            <th key={h} className={`px-2 py-1 font-medium ${i === 0 ? "text-left" : "text-right"}`}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="font-mono">
        {positions.length === 0 && (
          <tr>
            <td colSpan={HEADERS.length} className="px-2 py-3 text-center font-sans text-xs text-muted">
              No positions
            </td>
          </tr>
        )}
        {positions.map((p) => (
          <tr key={p.ticker} data-testid={`position-row-${p.ticker}`} className="border-t border-line/50">
            <td className="px-2 py-1 text-left font-sans font-semibold text-accent">{p.ticker}</td>
            <td data-testid={`position-qty-${p.ticker}`} className="px-2 py-1 text-right">
              {formatQty(p.quantity)}
            </td>
            <td className="px-2 py-1 text-right">{formatPrice(p.avg_cost)}</td>
            <td className="px-2 py-1 text-right">{formatPrice(p.current_price)}</td>
            <td className={`px-2 py-1 text-right ${signClass(p.unrealized_pnl)}`}>
              {formatUsd(p.unrealized_pnl)}
            </td>
            <td className={`px-2 py-1 text-right ${signClass(p.pnl_percent)}`}>
              {formatPercent(p.pnl_percent)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
