"use client";

import { useEffect, useState } from "react";
import type { Side } from "@/lib/types";

interface Props {
  selected: string | null;
  onTrade: (ticker: string, quantity: number, side: Side) => Promise<void>;
}

/** Market order entry: ticker, quantity, buy and sell buttons. */
export function TradeBar({ selected, onTrade }: Props) {
  const [ticker, setTicker] = useState(selected ?? "");
  const [quantity, setQuantity] = useState("1");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (selected) setTicker(selected);
  }, [selected]);

  async function trade(side: Side) {
    const t = ticker.trim().toUpperCase();
    setBusy(true);
    try {
      await onTrade(t, Number(quantity), side);
      setMessage({ ok: true, text: `${side === "buy" ? "Bought" : "Sold"} ${quantity} ${t}` });
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded border border-line bg-bg px-2 py-1 text-sm outline-none focus:border-primary";
  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-line bg-panel px-3 py-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">Trade</span>
      <input
        data-testid="trade-ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
        placeholder="Ticker"
        className={`${input} w-24 uppercase`}
      />
      <input
        data-testid="trade-quantity"
        type="number"
        min="0"
        step="any"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        className={`${input} w-24`}
      />
      <button
        data-testid="trade-buy"
        disabled={busy}
        onClick={() => trade("buy")}
        className="rounded bg-up px-4 py-1 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
      >
        Buy
      </button>
      <button
        data-testid="trade-sell"
        disabled={busy}
        onClick={() => trade("sell")}
        className="rounded bg-down px-4 py-1 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
      >
        Sell
      </button>
      {message && (
        <span data-testid="trade-message" className={`text-xs ${message.ok ? "text-up" : "text-down"}`}>
          {message.text}
        </span>
      )}
    </div>
  );
}
