import type { ChartPoint } from "@/lib/types";

const W = 80;
const H = 24;

/** Tiny SVG line of recent prices; green if up over the window, red if down. */
export function Sparkline({ points }: { points: ChartPoint[] }) {
  if (points.length < 2) return <svg width={W} height={H} />;
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const range = Math.max(...values) - min || 1;
  const coords = values
    .map((v, i) => `${(i / (values.length - 1)) * W},${H - ((v - min) / range) * H}`)
    .join(" ");
  const color = values[values.length - 1] >= values[0] ? "#26a69a" : "#ef5350";
  return (
    <svg width={W} height={H} data-testid="sparkline">
      <polyline points={coords} fill="none" stroke={color} strokeWidth="1.25" />
    </svg>
  );
}
