/** Small uppercase panel heading. */
export function PanelTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="border-b border-line px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted">
      {children}
    </h2>
  );
}
