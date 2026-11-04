import type {
  ChatResponse,
  Portfolio,
  Side,
  Snapshot,
  WatchlistItem,
} from "./types";

/** Fetch JSON from the same-origin API, throwing the backend `detail` on failure. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export const api = {
  portfolio: () => request<Portfolio>("/api/portfolio"),
  history: () =>
    request<{ snapshots: Snapshot[] }>("/api/portfolio/history").then((r) => r.snapshots),
  trade: (ticker: string, quantity: number, side: Side) =>
    request<{ portfolio: Portfolio }>("/api/portfolio/trade", {
      method: "POST",
      body: JSON.stringify({ ticker, quantity, side }),
    }),
  watchlist: () =>
    request<{ tickers: WatchlistItem[] }>("/api/watchlist").then((r) => r.tickers),
  addTicker: (ticker: string) =>
    request<WatchlistItem>("/api/watchlist", {
      method: "POST",
      body: JSON.stringify({ ticker }),
    }),
  removeTicker: (ticker: string) =>
    request<void>(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" }),
  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
