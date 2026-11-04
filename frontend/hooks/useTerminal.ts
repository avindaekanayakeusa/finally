"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChatMessage, Portfolio, Side, Snapshot, WatchlistItem } from "@/lib/types";

const HISTORY_REFRESH_MS = 30_000;

/** Server state for the terminal (portfolio, history, watchlist, chat) and the actions that change it. */
export function useTerminal() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [p, h, w] = await Promise.all([api.portfolio(), api.history(), api.watchlist()]);
    setPortfolio(p);
    setSnapshots(h);
    setWatchlist(w);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
    const id = setInterval(() => api.history().then(setSnapshots).catch(() => {}), HISTORY_REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  async function trade(ticker: string, quantity: number, side: Side) {
    const res = await api.trade(ticker, quantity, side);
    setPortfolio(res.portfolio);
    setSnapshots(await api.history());
  }

  async function addTicker(ticker: string) {
    const item = await api.addTicker(ticker);
    setWatchlist((w) => [...w, item]);
  }

  async function removeTicker(ticker: string) {
    await api.removeTicker(ticker);
    setWatchlist((w) => w.filter((i) => i.ticker !== ticker));
  }

  async function sendChat(text: string) {
    setMessages((m) => [...m, { role: "user", content: text }]);
    setChatLoading(true);
    setChatError(null);
    try {
      const res = await api.chat(text);
      setMessages((m) => [...m, { role: "assistant", content: res.message, actions: res.actions }]);
      await refresh();
    } catch (err) {
      setChatError((err as Error).message);
    } finally {
      setChatLoading(false);
    }
  }

  return {
    portfolio,
    snapshots,
    watchlist,
    messages,
    chatLoading,
    chatError,
    trade,
    addTicker,
    removeTicker,
    sendChat,
  };
}
