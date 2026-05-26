"use client";

import { motion } from "framer-motion";
import { computeMetrics } from "@/lib/metrics";
import type { Snapshot } from "@/lib/state";

function fmt(value: number, digits = 2, suffix = ""): string {
  if (!Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}${suffix}`;
}

function toneFromGood(value: number, threshold = 0): "good" | "bad" | "neutral" {
  if (value > threshold) return "good";
  if (value < -threshold) return "bad";
  return "neutral";
}

export function MetricsPanel({ snap }: { snap: Snapshot }) {
  const m = computeMetrics(snap);

  const tone: Record<string, "good" | "bad" | "neutral"> = {
    cagr: toneFromGood(m.cagr),
    sharpe: m.sharpe > 1 ? "good" : m.sharpe < 0 ? "bad" : "neutral",
    maxDd: "bad", // any drawdown is "downside"; we still show it red but informational
    alpha: toneFromGood(m.alphaVsBenchmark),
    winRate: m.winRate > 50 ? "good" : m.winRate < 40 ? "bad" : "neutral",
    pf: m.profitFactor > 1.2 ? "good" : m.profitFactor < 0.9 ? "bad" : "neutral",
  };

  const cells: { label: string; value: string; tone: "good" | "bad" | "neutral"; hint?: string }[] = [
    { label: "CAGR", value: fmt(m.cagr, 2, "%"), tone: tone.cagr, hint: "annualized return" },
    { label: "Sharpe", value: fmt(m.sharpe, 2), tone: tone.sharpe, hint: "ann. risk-adjusted" },
    {
      label: "Max DD",
      value: fmt(Math.abs(m.maxDrawdownPct), 2, "%"),
      tone: tone.maxDd,
      hint: `${m.maxDdDurationDays} samples`,
    },
    {
      label: `vs ${snap.benchmarkSymbol}`,
      value: fmt(m.alphaVsBenchmark, 2, "%"),
      tone: tone.alpha,
      hint: `bench ${fmt(m.benchmarkReturnPct, 2, "%")}`,
    },
    { label: "Win rate", value: fmt(m.winRate, 1, "%"), tone: tone.winRate, hint: `${m.nTrades} trades` },
    { label: "Profit factor", value: fmt(m.profitFactor, 2), tone: tone.pf, hint: "gross win / gross loss" },
  ];

  return (
    <section>
      <h3 className="text-xs uppercase tracking-[0.18em] text-muted mb-3">Performance</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {cells.map((c, i) => (
          <motion.div
            key={c.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: i * 0.04 }}
            className="glass rounded-2xl p-4"
          >
            <div className="text-[10px] uppercase tracking-wider text-muted">{c.label}</div>
            <div
              className={`mt-2 text-2xl font-semibold num ${
                c.tone === "good" ? "text-good" : c.tone === "bad" ? "text-bad" : "text-text"
              }`}
            >
              {c.value}
            </div>
            {c.hint && <div className="mt-1 text-[10px] text-mutedDim">{c.hint}</div>}
          </motion.div>
        ))}
      </div>
    </section>
  );
}
