"use client";

import { useEffect, useRef, useState } from "react";
import { formatPercent, formatPrice, signClass } from "@/lib/format";
import type { ChartPoint } from "@/lib/types";
import { Sparkline } from "./Sparkline";

const FLASH_MS = 150;

interface Props {
  ticker: string;
  price: number | null;
  changePercent: number;
  points: ChartPoint[];
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}

/** Briefly returns "flash-up"/"flash-down" when the price moves; the CSS transition fades it. */
export function useFlash(price: number | null): string {
  const prev = useRef(price);
  const [flash, setFlash] = useState("");

  useEffect(() => {
    const old = prev.current;
    prev.current = price;
    if (old === null || price === null || old === price) return;
    setFlash(price > old ? "flash-up" : "flash-down");
    const id = setTimeout(() => setFlash(""), FLASH_MS);
    return () => clearTimeout(id);
  }, [price]);

  return flash;
}

/** One watchlist row: ticker, flashing price, session change, sparkline, remove button. */
export function WatchlistRow(props: Props) {
  const { ticker, price, changePercent, points, selected, onSelect, onRemove } = props;
  const flash = useFlash(price);

  return (
    <tr
      data-testid={`watchlist-row-${ticker}`}
      onClick={() => onSelect(ticker)}
      className={`cursor-pointer border-b border-line/50 hover:bg-panel-2 ${selected ? "bg-panel-2" : ""}`}
    >
      <td className="px-2 py-1 font-semibold text-accent">{ticker}</td>
      <td
        data-testid={`price-${ticker}`}
        className={`px-2 py-1 text-right font-mono transition-colors duration-500 ${flash}`}
      >
        {price === null ? "--" : formatPrice(price)}
      </td>
      <td className={`px-2 py-1 text-right font-mono text-xs ${signClass(changePercent)}`}>
        {formatPercent(changePercent)}
      </td>
      <td className="px-2 py-1">
        <Sparkline points={points} />
      </td>
      <td className="px-1 py-1 text-right">
        <button
          data-testid={`remove-${ticker}`}
          aria-label={`Remove ${ticker}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove(ticker);
          }}
          className="px-1 text-muted hover:text-down"
        >
          x
        </button>
      </td>
    </tr>
  );
}
