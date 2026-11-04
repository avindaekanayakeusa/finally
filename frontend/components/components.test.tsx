import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage, Position } from "@/lib/types";
import { ChatPanel } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { PositionsTable } from "./PositionsTable";
import { WatchlistRow } from "./WatchlistRow";

const positions: Position[] = [
  { ticker: "AAPL", quantity: 10, avg_cost: 190, current_price: 200, market_value: 2000, unrealized_pnl: 100, pnl_percent: 5.26 },
  { ticker: "TSLA", quantity: 2, avg_cost: 250, current_price: 240, market_value: 480, unrealized_pnl: -20, pnl_percent: -4 },
];

function row(price: number | null) {
  return (
    <table>
      <tbody>
        <WatchlistRow
          ticker="AAPL"
          price={price}
          changePercent={1.5}
          points={[]}
          selected={false}
          onSelect={() => {}}
          onRemove={() => {}}
        />
      </tbody>
    </table>
  );
}

describe("Header", () => {
  it("shows total value, cash, and connection status", () => {
    render(<Header totalValue={10012.4} cash={8095} status="connected" />);
    expect(screen.getByTestId("total-value")).toHaveTextContent("$10,012.40");
    expect(screen.getByTestId("cash-balance")).toHaveTextContent("$8,095.00");
    expect(screen.getByTestId("connection-status")).toHaveAttribute("data-status", "connected");
  });
});

describe("WatchlistRow", () => {
  it("renders price and session change", () => {
    render(row(190.5));
    expect(screen.getByTestId("price-AAPL")).toHaveTextContent("190.50");
    expect(screen.getByTestId("watchlist-row-AAPL")).toHaveTextContent("+1.50%");
  });

  it("flashes green on uptick and red on downtick, then clears", () => {
    vi.useFakeTimers();
    const { rerender } = render(row(100));
    const cell = screen.getByTestId("price-AAPL");
    expect(cell.className).not.toMatch(/flash-/);

    rerender(row(101));
    expect(cell).toHaveClass("flash-up");

    act(() => vi.advanceTimersByTime(500));
    expect(cell.className).not.toMatch(/flash-/);

    rerender(row(99));
    expect(cell).toHaveClass("flash-down");
    vi.useRealTimers();
  });
});

describe("PositionsTable", () => {
  it("renders a row per position", () => {
    render(<PositionsTable positions={positions} />);
    expect(screen.getByTestId("position-row-AAPL")).toHaveTextContent("$100.00");
    expect(screen.getByTestId("position-row-TSLA")).toHaveTextContent("-4.00%");
  });

  it("shows an empty state", () => {
    render(<PositionsTable positions={[]} />);
    expect(screen.getByText("No positions")).toBeInTheDocument();
  });
});

describe("Heatmap", () => {
  it("colors cells by profit or loss", () => {
    render(<Heatmap positions={positions} />);
    expect(screen.getByTestId("heatmap-cell-AAPL")).toHaveAttribute("data-pnl", "profit");
    expect(screen.getByTestId("heatmap-cell-TSLA")).toHaveAttribute("data-pnl", "loss");
  });
});

describe("ChatPanel", () => {
  const messages: ChatMessage[] = [
    { role: "user", content: "Buy 5 NVDA" },
    {
      role: "assistant",
      content: "Bought 5 NVDA.",
      actions: {
        trades: [{ ticker: "NVDA", side: "buy", quantity: 5, status: "executed", price: 875.2, error: null }],
        watchlist_changes: [{ ticker: "PYPL", action: "add", status: "failed", error: "already on watchlist" }],
      },
    },
  ];

  it("renders messages and inline actions", () => {
    render(<ChatPanel messages={messages} loading={false} error={null} onSend={() => {}} />);
    expect(screen.getByTestId("chat-message-user")).toHaveTextContent("Buy 5 NVDA");
    const actions = screen.getAllByTestId("chat-action");
    expect(actions.map((a) => a.textContent)).toEqual([
      "Watchlist add PYPL failed: already on watchlist",
      "BUY 5 NVDA @ 875.20",
    ]);
  });

  it("shows loading indicator and disables send while waiting", () => {
    render(<ChatPanel messages={[]} loading={true} error={null} onSend={() => {}} />);
    expect(screen.getByTestId("chat-loading")).toBeInTheDocument();
    expect(screen.getByTestId("chat-send")).toBeDisabled();
  });

  it("sends the typed message and clears the input", async () => {
    const onSend = vi.fn();
    render(<ChatPanel messages={[]} loading={false} error={null} onSend={onSend} />);
    await userEvent.type(screen.getByTestId("chat-input"), "hello");
    await userEvent.click(screen.getByTestId("chat-send"));
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(screen.getByTestId("chat-input")).toHaveValue("");
  });
});
