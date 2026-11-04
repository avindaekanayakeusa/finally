"use client";

import { useState } from "react";
import { sessionChangePercent } from "@/lib/portfolio";
import type { PriceStream } from "@/hooks/usePriceStream";
import type { WatchlistItem } from "@/lib/types";
import { PanelTitle } from "./PanelTitle";
import { WatchlistRow } from "./WatchlistRow";

interface Props {
  items: WatchlistItem[];
  stream: PriceStream;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<void>;
  onRemove: (ticker: string) => void;
}

/** Watchlist panel with live rows and an add-ticker form. */
export function Watchlist({ items, stream, selected, onSelect, onAdd, onRemove }: Props) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const ticker = input.trim().toUpperCase();
    if (!ticker) return;
    try {
      await onAdd(ticker);
      setInput("");
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="flex min-h-0 flex-col" data-testid="watchlist">
      <PanelTitle>Watchlist</PanelTitle>
      <form onSubmit={submit} className="flex gap-1 border-b border-line p-2">
        <input
          data-testid="watchlist-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Add ticker"
          className="w-full rounded border border-line bg-bg px-2 py-1 text-sm uppercase outline-none focus:border-primary"
        />
        <button
          data-testid="watchlist-add"
          className="rounded bg-primary px-3 text-sm font-semibold text-bg hover:opacity-90"
        >
          Add
        </button>
      </form>
      {error && <p data-testid="watchlist-error" className="px-2 py-1 text-xs text-down">{error}</p>}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full text-sm">
          <tbody>
            {items.map(({ ticker }) => {
              const price = stream.prices[ticker]?.price ?? null;
              return (
                <WatchlistRow
                  key={ticker}
                  ticker={ticker}
                  price={price}
                  changePercent={price === null ? 0 : sessionChangePercent(stream.sessionStart[ticker], price)}
                  points={stream.history[ticker] ?? []}
                  selected={ticker === selected}
                  onSelect={onSelect}
                  onRemove={onRemove}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

