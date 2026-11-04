const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

/** Format a number as US dollars, e.g. $1,234.50. */
export function formatUsd(value: number): string {
  return usd.format(value);
}

/** Format a price with two decimals and no currency symbol. */
export function formatPrice(value: number): string {
  return value.toFixed(2);
}

/** Format a percent-unit number with sign, e.g. +1.23%. */
export function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

/** Format a quantity, trimming trailing zeros on fractional shares. */
export function formatQty(value: number): string {
  return Number(value.toFixed(4)).toString();
}

/** Tailwind text color class for a signed value. */
export function signClass(value: number): string {
  if (value > 0) return "text-up";
  if (value < 0) return "text-down";
  return "text-muted";
}
