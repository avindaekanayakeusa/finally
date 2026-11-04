"use client";

import { useEffect, useRef, useState } from "react";
import { formatPrice, formatQty } from "@/lib/format";
import type { ChatActions, ChatMessage } from "@/lib/types";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  error: string | null;
  onSend: (text: string) => void;
}

/** Collapsible AI assistant sidebar with history, loading state, and inline action results. */
export function ChatPanel({ messages, loading, error, onSend }: Props) {
  const [open, setOpen] = useState(true);
  const [input, setInput] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [messages, loading]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    onSend(text);
    setInput("");
  }

  if (!open) {
    return (
      <button
        data-testid="chat-toggle"
        onClick={() => setOpen(true)}
        className="border-l border-line bg-panel px-2 text-xs font-semibold uppercase tracking-wider text-accent [writing-mode:vertical-rl]"
      >
        AI Assistant
      </button>
    );
  }

  return (
    <aside data-testid="chat-panel" className="flex w-80 shrink-0 flex-col border-l border-line bg-panel">
      <div className="flex items-center border-b border-line px-3 py-1.5">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-accent">AI Assistant</h2>
        <button
          data-testid="chat-toggle"
          onClick={() => setOpen(false)}
          aria-label="Collapse chat"
          className="ml-auto text-muted hover:text-fg"
        >
          &raquo;
        </button>
      </div>
      <div data-testid="chat-messages" className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 text-sm">
        {messages.length === 0 && (
          <p className="text-xs text-muted">Ask about your portfolio, or say &quot;buy 5 AAPL&quot;.</p>
        )}
        {messages.map((m, i) => (
          <Message key={i} message={m} />
        ))}
        {loading && (
          <p data-testid="chat-loading" className="animate-pulse text-xs text-muted">
            FinAlly is thinking...
          </p>
        )}
        {error && <p data-testid="chat-error" className="text-xs text-down">{error}</p>}
        <div ref={end} />
      </div>
      <form onSubmit={submit} className="flex gap-1 border-t border-line p-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message FinAlly"
          className="w-full rounded border border-line bg-bg px-2 py-1 text-sm outline-none focus:border-primary"
        />
        <button
          data-testid="chat-send"
          disabled={loading}
          className="rounded bg-secondary px-3 text-sm font-semibold text-fg hover:opacity-90 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </aside>
  );
}

function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div
      data-testid={`chat-message-${message.role}`}
      className={`rounded px-2 py-1.5 ${isUser ? "ml-6 bg-primary/15" : "mr-6 bg-panel-2"}`}
    >
      <p className="whitespace-pre-wrap">{message.content}</p>
      {message.actions && <Actions actions={message.actions} />}
    </div>
  );
}

function Actions({ actions }: { actions: ChatActions }) {
  const lines = [
    ...actions.watchlist_changes.map((w) => ({
      ok: w.status === "executed",
      text: `Watchlist ${w.action} ${w.ticker}`,
      error: w.error,
    })),
    ...actions.trades.map((t) => ({
      ok: t.status === "executed",
      text: `${t.side.toUpperCase()} ${formatQty(t.quantity)} ${t.ticker}${t.price ? ` @ ${formatPrice(t.price)}` : ""}`,
      error: t.error,
    })),
  ];
  if (lines.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5 border-t border-line pt-1 text-xs">
      {lines.map((l, i) => (
        <li key={i} data-testid="chat-action" data-status={l.ok ? "executed" : "failed"} className={l.ok ? "text-up" : "text-down"}>
          {l.ok ? l.text : `${l.text} failed: ${l.error}`}
        </li>
      ))}
    </ul>
  );
}
