import { formatUsd } from "@/lib/format";
import type { ConnectionStatus } from "@/lib/types";

const DOT: Record<ConnectionStatus, string> = {
  connected: "bg-green-500",
  reconnecting: "bg-yellow-400",
  disconnected: "bg-red-500",
};

interface Props {
  totalValue: number | null;
  cash: number | null;
  status: ConnectionStatus;
}

/** Top bar: brand, live total value, cash, and SSE connection status. */
export function Header({ totalValue, cash, status }: Props) {
  return (
    <header className="flex items-center gap-6 border-b border-line bg-panel px-4 py-2">
      <h1 className="text-lg font-bold tracking-wide text-accent">
        Fin<span className="text-primary">Ally</span>
      </h1>
      <Stat label="Total Value" testId="total-value" value={totalValue} />
      <Stat label="Cash" testId="cash-balance" value={cash} />
      <div className="ml-auto flex items-center gap-2 text-xs text-muted">
        <span
          data-testid="connection-status"
          data-status={status}
          className={`h-2.5 w-2.5 rounded-full ${DOT[status]}`}
        />
        <span className="uppercase">{status}</span>
      </div>
    </header>
  );
}

function Stat({ label, value, testId }: { label: string; value: number | null; testId: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[10px] uppercase text-muted">{label}</span>
      <span data-testid={testId} className="font-mono text-sm">
        {value === null ? "--" : formatUsd(value)}
      </span>
    </div>
  );
}
