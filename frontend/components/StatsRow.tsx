"use client";

import { motion } from "framer-motion";
import { CountUp } from "@/components/CountUp";
import type { Snapshot } from "@/lib/state";

const SYMBOL: Record<string, string> = { INR: "₹", USD: "$" };

interface StatProps {
  label: string;
  value: number;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  tone?: "good" | "bad" | "neutral";
  signed?: boolean;
  delay?: number;
}

function Stat({ label, value, decimals = 2, prefix = "", suffix = "", tone, signed, delay = 0 }: StatProps) {
  const toneClass =
    tone === "good" ? "text-good" : tone === "bad" ? "text-bad" : "text-text";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className="glass rounded-2xl p-5 hover:glass-hi transition-colors group"
    >
      <div className="text-[10px] tracking-[0.18em] uppercase text-muted">{label}</div>
      <div className={`mt-2 text-2xl sm:text-3xl font-semibold num ${toneClass}`}>
        <CountUp value={value} decimals={decimals} prefix={prefix} suffix={suffix} signed={signed} />
      </div>
    </motion.div>
  );
}

export function StatsRow({ snap }: { snap: Snapshot }) {
  const sym = SYMBOL[snap.currency] || "$";

  // 1d change from last two equity points (if present)
  const eq = snap.equityHistory;
  const dailyChangePct =
    eq.length >= 2 && eq[eq.length - 2].value > 0
      ? ((eq[eq.length - 1].value - eq[eq.length - 2].value) / eq[eq.length - 2].value) * 100
      : 0;

  const dailyChangeAbs =
    eq.length >= 2 ? eq[eq.length - 1].value - eq[eq.length - 2].value : 0;

  return (
    <section className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      <Stat
        label="Cash"
        value={snap.cash}
        prefix={sym}
        decimals={0}
        delay={0.0}
      />
      <Stat
        label="Today (Δ)"
        value={dailyChangeAbs}
        prefix={sym}
        signed
        decimals={0}
        tone={dailyChangeAbs > 0 ? "good" : dailyChangeAbs < 0 ? "bad" : "neutral"}
        delay={0.05}
      />
      <Stat
        label="Today (%)"
        value={dailyChangePct}
        suffix="%"
        signed
        tone={dailyChangePct > 0 ? "good" : dailyChangePct < 0 ? "bad" : "neutral"}
        delay={0.1}
      />
      <Stat
        label="Unrealized P&L"
        value={snap.unrealizedPnl}
        prefix={sym}
        signed
        decimals={0}
        tone={snap.unrealizedPnl > 0 ? "good" : snap.unrealizedPnl < 0 ? "bad" : "neutral"}
        delay={0.15}
      />
    </section>
  );
}
