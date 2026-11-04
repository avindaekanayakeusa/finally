import { formatPercent } from "@/lib/format";
import { treemap } from "@/lib/treemap";
import type { Position } from "@/lib/types";

/** Background color scaled by P&L percent: green for profit, red for loss, saturating at 5%. */
export function pnlColor(pnlPercent: number): string {
  const intensity = Math.min(Math.abs(pnlPercent) / 5, 1);
  const alpha = (0.25 + 0.65 * intensity).toFixed(2);
  return pnlPercent >= 0 ? `rgba(38, 166, 154, ${alpha})` : `rgba(239, 83, 80, ${alpha})`;
}

/** Treemap of positions sized by market value and colored by unrealized P&L. */
export function Heatmap({ positions }: { positions: Position[] }) {
  const byTicker = new Map(positions.map((p) => [p.ticker, p]));
  const rects = treemap(positions.map((p) => ({ id: p.ticker, weight: p.market_value })));

  return (
    <div data-testid="heatmap" className="relative h-full w-full">
      {rects.length === 0 && (
        <p className="flex h-full items-center justify-center text-xs text-muted">No positions</p>
      )}
      {rects.map((r) => {
        const p = byTicker.get(r.id)!;
        return (
          <div
            key={r.id}
            data-testid={`heatmap-cell-${r.id}`}
            data-pnl={p.unrealized_pnl >= 0 ? "profit" : "loss"}
            className="absolute flex flex-col items-center justify-center overflow-hidden border border-bg text-xs"
            style={{
              left: `${r.x}%`,
              top: `${r.y}%`,
              width: `${r.w}%`,
              height: `${r.h}%`,
              backgroundColor: pnlColor(p.pnl_percent),
            }}
          >
            <span className="font-semibold">{r.id}</span>
            <span className="font-mono">{formatPercent(p.pnl_percent)}</span>
          </div>
        );
      })}
    </div>
  );
}
