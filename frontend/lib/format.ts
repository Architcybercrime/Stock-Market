// Currency and number formatters used across the dashboard.

export type Currency = "INR" | "USD";

const SYMBOL: Record<Currency, string> = { INR: "₹", USD: "$" };

const COMPACT_FORMATTER = new Intl.NumberFormat("en-IN", {
  notation: "compact",
  maximumFractionDigits: 1,
});

export function money(value: number, currency: Currency = "INR"): string {
  const sym = SYMBOL[currency];
  if (!Number.isFinite(value)) return `${sym} —`;
  const abs = Math.abs(value);
  const formatted =
    abs >= 1_000_000
      ? abs.toLocaleString("en-IN", { maximumFractionDigits: 0 })
      : abs.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${value < 0 ? "−" : ""}${sym}${formatted}`;
}

export function moneyCompact(value: number, currency: Currency = "INR"): string {
  const sym = SYMBOL[currency];
  if (!Number.isFinite(value)) return `${sym}—`;
  return `${value < 0 ? "−" : ""}${sym}${COMPACT_FORMATTER.format(Math.abs(value))}`;
}

export function percent(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(digits)}%`;
}

export function relativeTime(iso: string): string {
  try {
    const t = new Date(iso).getTime();
    if (Number.isNaN(t)) return "—";
    const diff = (Date.now() - t) / 1000;
    if (diff < 60) return `${Math.floor(diff)}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  } catch {
    return "—";
  }
}

export function shortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-IN", {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export function symbolColor(value: number): string {
  if (value > 0) return "text-good";
  if (value < 0) return "text-bad";
  return "text-muted";
}
