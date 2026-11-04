"use client";

import { useEffect, useRef } from "react";
import {
  AreaSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { toChartData } from "@/lib/portfolio";
import type { ChartPoint } from "@/lib/types";

interface Props {
  points: ChartPoint[];
  color: string;
  testId: string;
}

/** Canvas area chart (Lightweight Charts) that redraws when `points` change. */
export function LineChart({ points, color, testId }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const chart = useRef<IChartApi | null>(null);

  useEffect(() => {
    const c = createChart(container.current!, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#8b949e" },
      grid: { vertLines: { color: "#21262d" }, horzLines: { color: "#21262d" } },
      rightPriceScale: { borderColor: "#30363d" },
      timeScale: { borderColor: "#30363d", timeVisible: true, secondsVisible: true },
    });
    series.current = c.addSeries(AreaSeries, {
      lineColor: color,
      topColor: `${color}55`,
      bottomColor: `${color}05`,
      lineWidth: 2,
    });
    chart.current = c;
    return () => c.remove();
  }, [color]);

  useEffect(() => {
    const data = toChartData(points).map((p) => ({ time: p.time as UTCTimestamp, value: p.value }));
    series.current?.setData(data);
    chart.current?.timeScale().fitContent();
  }, [points, color]);

  return <div ref={container} data-testid={testId} data-points={points.length} className="h-full w-full" />;
}
