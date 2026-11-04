/** Types mirroring the backend contract in planning/PLAN.md sections 6 and 8. */

export type Direction = "up" | "down" | "flat";

export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  timestamp: number;
  change: number;
  change_percent: number;
  direction: Direction;
}

export type PriceMap = Record<string, PriceUpdate>;

export interface Position {
  ticker: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_percent: number;
}

export interface Portfolio {
  cash_balance: number;
  total_value: number;
  positions_value: number;
  unrealized_pnl: number;
  positions: Position[];
}

export interface Snapshot {
  total_value: number;
  recorded_at: string;
}

export interface WatchlistItem {
  ticker: string;
  price: number | null;
  previous_price: number | null;
  direction: Direction | null;
  added_at: string;
}

export type Side = "buy" | "sell";

export interface TradeAction {
  ticker: string;
  side: Side;
  quantity: number;
  status: "executed" | "failed";
  price?: number | null;
  error: string | null;
}

export interface WatchlistAction {
  ticker: string;
  action: "add" | "remove";
  status: "executed" | "failed";
  error: string | null;
}

export interface ChatActions {
  trades: TradeAction[];
  watchlist_changes: WatchlistAction[];
}

export interface ChatResponse {
  message: string;
  actions: ChatActions;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  actions?: ChatActions;
}

export interface ChartPoint {
  time: number;
  value: number;
}

export type ConnectionStatus = "connected" | "reconnecting" | "disconnected";
