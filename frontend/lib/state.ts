// Fetch & normalize the paper_state.json file written by the daemon and
// snapshot workflow. Reads from raw.githubusercontent.com so the static
// dashboard can refresh data without any backend server.

import type { Currency } from "@/lib/format";

export interface PaperOrder {
  id: string;
  client_order_id: string;
  strategy: string;
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  type: string;
  status: string;
  filled_qty: string;
  avg_fill_price: string | null;
  fee: string;
  reject_reason: string | null;
  created_at: string;
}

export interface PaperFill {
  id: string;
  order_id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  price: string;
  fee: string;
  venue: string;
  ts: string;
}

export interface PaperState {
  schema_version: number;
  cash: string;
  initial_capital: string;
  realized_pnl: string;
  positions: Record<string, string>;
  avg_costs: Record<string, string>;
  orders: PaperOrder[];
  fills: PaperFill[];
  equity_history: [string, string][];
  benchmark_symbol?: string;
  benchmark_history?: [string, string][];
  last_prices: Record<string, number>;
  mark_to_market_equity: number | null;
  currency: Currency;
  updated_at: string;
  snapshot_at: string | null;
}

export interface DerivedPosition {
  symbol: string;
  qty: number;
  avgCost: number;
  lastPrice: number;
  marketValue: number;
  costBasis: number;
  unrealizedPnL: number;
  unrealizedPct: number;
  weight: number;
}

export interface Snapshot {
  raw: PaperState;
  currency: Currency;
  cash: number;
  initialCapital: number;
  realizedPnl: number;
  unrealizedPnl: number;
  nav: number;
  totalReturnPct: number;
  positions: DerivedPosition[];
  fills: PaperFill[];
  orders: PaperOrder[];
  equityHistory: { ts: string; value: number }[];
  benchmarkSymbol: string;
  benchmarkHistory: { ts: string; value: number }[];
  updatedAt: string;
  snapshotAt: string | null;
}

const DEFAULT_STATE_URL =
  process.env.NEXT_PUBLIC_STATE_URL ||
  "https://raw.githubusercontent.com/Architcybercrime/Stock-Market/main/data/paper_state.json";

export async function fetchState(url: string = DEFAULT_STATE_URL): Promise<Snapshot> {
  const cacheBuster = `?t=${Math.floor(Date.now() / 60000)}`;
  const res = await fetch(`${url}${cacheBuster}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`state fetch failed: ${res.status} ${res.statusText}`);
  }
  const raw = (await res.json()) as PaperState;
  return deriveSnapshot(raw);
}

export function deriveSnapshot(raw: PaperState): Snapshot {
  const currency: Currency = (raw.currency as Currency) || "INR";
  const cash = Number(raw.cash) || 0;
  const initialCapital = Number(raw.initial_capital) || 100_000;
  const realizedPnl = Number(raw.realized_pnl) || 0;
  const lastPrices = raw.last_prices || {};

  let positionsTotal = 0;
  const positions: DerivedPosition[] = Object.entries(raw.positions || {})
    .map(([symbol, qtyStr]) => {
      const qty = Number(qtyStr);
      if (qty === 0) return null;
      const avgCost = Number(raw.avg_costs?.[symbol] ?? 0);
      const lastPrice = Number(lastPrices[symbol] ?? avgCost);
      const marketValue = qty * lastPrice;
      const costBasis = qty * avgCost;
      const unrealizedPnL = marketValue - costBasis;
      const unrealizedPct = costBasis !== 0 ? (unrealizedPnL / costBasis) * 100 : 0;
      positionsTotal += marketValue;
      return {
        symbol,
        qty,
        avgCost,
        lastPrice,
        marketValue,
        costBasis,
        unrealizedPnL,
        unrealizedPct,
        weight: 0, // computed after we know the total
      };
    })
    .filter((p): p is DerivedPosition => p !== null);

  const nav = cash + positionsTotal;
  const unrealizedPnl = positionsTotal - positions.reduce((sum, p) => sum + p.costBasis, 0);
  const totalReturnPct = initialCapital > 0 ? ((nav - initialCapital) / initialCapital) * 100 : 0;

  // Weights as a share of total NAV (cash counted separately in UI).
  positions.forEach((p) => {
    p.weight = nav > 0 ? (p.marketValue / nav) * 100 : 0;
  });

  // Sort by absolute market value desc so the dashboard highlights the largest.
  positions.sort((a, b) => b.marketValue - a.marketValue);

  const equityHistory = (raw.equity_history || []).map(([ts, value]) => ({
    ts,
    value: Number(value),
  }));
  const benchmarkHistory = (raw.benchmark_history || []).map(([ts, value]) => ({
    ts,
    value: Number(value),
  }));

  return {
    raw,
    currency,
    cash,
    initialCapital,
    realizedPnl,
    unrealizedPnl,
    nav,
    totalReturnPct,
    positions,
    fills: raw.fills || [],
    orders: raw.orders || [],
    equityHistory,
    benchmarkSymbol: raw.benchmark_symbol || "^NSEI",
    benchmarkHistory,
    updatedAt: raw.updated_at,
    snapshotAt: raw.snapshot_at ?? null,
  };
}

// Empty-state placeholder so the UI can render meaningfully before the daemon
// has produced any data yet.
export function placeholderSnapshot(): Snapshot {
  const empty: PaperState = {
    schema_version: 1,
    cash: "1000000",
    initial_capital: "1000000",
    realized_pnl: "0",
    positions: {},
    avg_costs: {},
    orders: [],
    fills: [],
    equity_history: [],
    benchmark_symbol: "^NSEI",
    benchmark_history: [],
    last_prices: {},
    mark_to_market_equity: null,
    currency: "INR",
    updated_at: new Date().toISOString(),
    snapshot_at: null,
  };
  return deriveSnapshot(empty);
}
