"use client";

import { useState } from "react";
import { usePriceStream } from "@/hooks/usePriceStream";
import { useTerminal } from "@/hooks/useTerminal";
import { applyLivePrices } from "@/lib/portfolio";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { LineChart } from "./LineChart";
import { PanelTitle } from "./PanelTitle";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { Watchlist } from "./Watchlist";

/** The full trading workstation layout. */
export function Terminal() {
  const stream = usePriceStream();
  const t = useTerminal();
  const [picked, setPicked] = useState<string | null>(null);

  const selected = picked ?? t.watchlist[0]?.ticker ?? null;
  const live = t.portfolio ? applyLivePrices(t.portfolio, stream.prices) : null;
  const pnlPoints = t.snapshots.map((s) => ({
    time: Date.parse(s.recorded_at) / 1000,
    value: s.total_value,
  }));

  return (
    <div className="flex h-screen flex-col">
      <Header totalValue={live?.total_value ?? null} cash={live?.cash_balance ?? null} status={stream.status} />
      <div className="flex min-h-0 flex-1">
        <aside className="flex w-80 shrink-0 flex-col border-r border-line bg-panel">
          <Watchlist
            items={t.watchlist}
            stream={stream}
            selected={selected}
            onSelect={setPicked}
            onAdd={t.addTicker}
            onRemove={(ticker) => t.removeTicker(ticker).catch(() => {})}
          />
        </aside>
        <main className="grid min-w-0 flex-1 grid-cols-2 grid-rows-[3fr_2fr] gap-px bg-line">
          <Panel title={selected ? `${selected} - Price` : "Price"} className="col-span-2">
            <LineChart
              points={selected ? stream.history[selected] ?? [] : []}
              color="#209dd7"
              testId="main-chart"
            />
          </Panel>
          <Panel title="Portfolio Heatmap">
            <Heatmap positions={live?.positions ?? []} />
          </Panel>
          <Panel title="Portfolio Value">
            <LineChart points={pnlPoints} color="#ecad0a" testId="pnl-chart" />
          </Panel>
        </main>
        <ChatPanel messages={t.messages} loading={t.chatLoading} error={t.chatError} onSend={t.sendChat} />
      </div>
      <section className="max-h-48 overflow-y-auto border-t border-line bg-panel">
        <PanelTitle>Positions</PanelTitle>
        <PositionsTable positions={live?.positions ?? []} />
      </section>
      <TradeBar selected={selected} onTrade={t.trade} />
    </div>
  );
}

function Panel({ title, className = "", children }: { title: string; className?: string; children: React.ReactNode }) {
  return (
    <section className={`flex min-h-0 flex-col bg-panel ${className}`}>
      <PanelTitle>{title}</PanelTitle>
      <div className="min-h-0 flex-1 p-2">{children}</div>
    </section>
  );
}
