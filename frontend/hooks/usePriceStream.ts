"use client";

import { useEffect, useState } from "react";
import type { ChartPoint, ConnectionStatus, PriceMap } from "@/lib/types";

const MAX_POINTS = 600;

export interface PriceStream {
  prices: PriceMap;
  history: Record<string, ChartPoint[]>;
  sessionStart: Record<string, number>;
  status: ConnectionStatus;
}

/** Append each ticker's latest price to its history, capped at MAX_POINTS. */
export function appendHistory(
  history: Record<string, ChartPoint[]>,
  prices: PriceMap,
): Record<string, ChartPoint[]> {
  const next = { ...history };
  for (const [ticker, p] of Object.entries(prices)) {
    const points = next[ticker] ?? [];
    const last = points[points.length - 1];
    if (last && last.time === p.timestamp) continue;
    next[ticker] = [...points, { time: p.timestamp, value: p.price }].slice(-MAX_POINTS);
  }
  return next;
}

/** Subscribe to /api/stream/prices and accumulate prices, history, and connection status. */
export function usePriceStream(): PriceStream {
  const [state, setState] = useState<PriceStream>({
    prices: {},
    history: {},
    sessionStart: {},
    status: "reconnecting",
  });

  useEffect(() => {
    const source = new EventSource("/api/stream/prices");
    source.onopen = () => setState((s) => ({ ...s, status: "connected" }));
    source.onerror = () =>
      setState((s) => ({
        ...s,
        status: source.readyState === EventSource.CLOSED ? "disconnected" : "reconnecting",
      }));
    source.onmessage = (event) => {
      const prices: PriceMap = JSON.parse(event.data);
      setState((s) => {
        const sessionStart = { ...s.sessionStart };
        for (const [t, p] of Object.entries(prices)) sessionStart[t] ??= p.price;
        return {
          prices,
          history: appendHistory(s.history, prices),
          sessionStart,
          status: "connected",
        };
      });
    };
    return () => source.close();
  }, []);

  return state;
}
