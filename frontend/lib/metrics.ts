// Performance metrics computed client-side from equity history + fills.
//
// Why client-side: keeps the dashboard self-contained against the committed
// state file. No need for a separate metrics-computation step in CI.

import type { Snapshot } from "@/lib/state";

export interface PerfMetrics {
  totalReturnPct: number;
  cagr: number;            // annualized return
  annVolPct: number;       // annualized vol (stdev of daily returns × sqrt(252))
  sharpe: number;
  maxDrawdownPct: number;
  maxDdDurationDays: number;
  winRate: number;
  profitFactor: number;
  nTrades: number;
  expectancy: number;      // average P&L per round-trip
  // Benchmark relative
  alphaVsBenchmark: number; // your return − benchmark return, over the same window
  benchmarkReturnPct: number;
}

const PERIODS_PER_YEAR = 252;

function dailyReturns(series: { ts: string; value: number }[]): number[] {
  if (series.length < 2) return [];
  const rets: number[] = [];
  for (let i = 1; i < series.length; i++) {
    const prev = series[i - 1].value;
    const curr = series[i].value;
    if (prev > 0) rets.push(curr / prev - 1);
  }
  return rets;
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0;
  const m = mean(xs);
  const v = xs.reduce((s, x) => s + (x - m) ** 2, 0) / (xs.length - 1);
  return Math.sqrt(v);
}

function maxDrawdown(series: { value: number }[]): { ddPct: number; durationSamples: number } {
  if (series.length < 2) return { ddPct: 0, durationSamples: 0 };
  let peak = series[0].value;
  let maxDd = 0;
  let curDur = 0;
  let maxDur = 0;
  for (const p of series) {
    if (p.value > peak) {
      peak = p.value;
      curDur = 0;
    } else {
      const dd = peak > 0 ? p.value / peak - 1 : 0;
      if (dd < maxDd) maxDd = dd;
      curDur += 1;
      if (curDur > maxDur) maxDur = curDur;
    }
  }
  return { ddPct: maxDd, durationSamples: maxDur };
}

function roundTripStats(snap: Snapshot): { wins: number; losses: number; pf: number; expectancy: number; n: number } {
  // FIFO match buys against sells per symbol.
  type Lot = { qty: number; price: number };
  const lots: Record<string, Lot[]> = {};
  const pnls: number[] = [];

  const sorted = [...snap.fills].sort((a, b) => (a.ts < b.ts ? -1 : 1));
  for (const f of sorted) {
    const qty = Number(f.qty);
    const price = Number(f.price);
    const fee = Number(f.fee);
    const sym = f.symbol;
    if (!lots[sym]) lots[sym] = [];
    if (f.side === "buy") {
      lots[sym].push({ qty, price });
    } else {
      let remaining = qty;
      while (remaining > 0 && lots[sym].length > 0) {
        const lot = lots[sym][0];
        const take = Math.min(remaining, lot.qty);
        const pnl = (price - lot.price) * take - fee * (take / qty);
        pnls.push(pnl);
        lot.qty -= take;
        remaining -= take;
        if (lot.qty === 0) lots[sym].shift();
      }
    }
  }

  if (!pnls.length) return { wins: 0, losses: 0, pf: 0, expectancy: 0, n: 0 };
  const wins = pnls.filter((p) => p > 0);
  const losses = pnls.filter((p) => p < 0);
  const grossWin = wins.reduce((s, x) => s + x, 0);
  const grossLoss = Math.abs(losses.reduce((s, x) => s + x, 0));
  const pf = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0;
  return {
    wins: wins.length,
    losses: losses.length,
    pf,
    expectancy: mean(pnls),
    n: pnls.length,
  };
}

export function computeMetrics(snap: Snapshot): PerfMetrics {
  const equity = snap.equityHistory;
  const rets = dailyReturns(equity);
  const totalReturn = snap.totalReturnPct;
  const yearsApprox = Math.max(equity.length / PERIODS_PER_YEAR, 1 / PERIODS_PER_YEAR);

  const cagr =
    equity.length >= 2 && equity[0].value > 0
      ? (snap.nav / equity[0].value) ** (1 / yearsApprox) - 1
      : 0;
  const annVol = stdev(rets) * Math.sqrt(PERIODS_PER_YEAR);
  const sharpe = annVol > 0 ? (mean(rets) / stdev(rets)) * Math.sqrt(PERIODS_PER_YEAR) : 0;
  const { ddPct, durationSamples } = maxDrawdown(equity);
  const rt = roundTripStats(snap);
  const winRate = rt.n > 0 ? rt.wins / rt.n : 0;

  // Benchmark — index its first value to your equity's first value, compute the
  // implied benchmark NAV, then take the return over the same window.
  let benchReturn = 0;
  if (snap.benchmarkHistory.length >= 2 && equity.length >= 1) {
    const first = snap.benchmarkHistory[0].value;
    const last = snap.benchmarkHistory[snap.benchmarkHistory.length - 1].value;
    if (first > 0) benchReturn = (last / first - 1) * 100;
  }

  return {
    totalReturnPct: totalReturn,
    cagr: cagr * 100,
    annVolPct: annVol * 100,
    sharpe,
    maxDrawdownPct: ddPct * 100,
    maxDdDurationDays: durationSamples,
    winRate: winRate * 100,
    profitFactor: rt.pf,
    nTrades: rt.n,
    expectancy: rt.expectancy,
    alphaVsBenchmark: totalReturn - benchReturn,
    benchmarkReturnPct: benchReturn,
  };
}
