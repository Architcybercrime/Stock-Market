"use client";

import dynamic from "next/dynamic";
import { motion } from "framer-motion";
import { CountUp } from "@/components/CountUp";
import type { Snapshot } from "@/lib/state";
import { percent, relativeTime } from "@/lib/format";

// Three.js is heavy and SSR-incompatible. Lazy-load.
const HeroOrb = dynamic(
  () => import("@/components/HeroOrb").then((m) => m.HeroOrb),
  { ssr: false, loading: () => null }
);

const SYMBOL: Record<string, string> = { INR: "₹", USD: "$" };

export function HeroCard({ snap }: { snap: Snapshot }) {
  const tone = snap.totalReturnPct > 0 ? "good" : snap.totalReturnPct < 0 ? "bad" : "neutral";
  const sym = SYMBOL[snap.currency] || "$";
  const lastUpdate = snap.snapshotAt || snap.updatedAt;

  return (
    <motion.section
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      className="relative overflow-hidden rounded-3xl glass p-6 sm:p-10 min-h-[320px] flex items-center"
    >
      {/* 3D orb behind the text */}
      <div className="absolute right-[-10%] sm:right-[-2%] top-1/2 -translate-y-1/2 w-[60%] sm:w-[50%] h-[120%] pointer-events-auto">
        <HeroOrb tone={tone} />
      </div>

      {/* Foreground */}
      <div className="relative z-10 max-w-xl">
        <div className="flex items-center gap-3 text-xs text-muted uppercase tracking-[0.2em] mb-3">
          <span className="inline-block h-2 w-2 rounded-full bg-good animate-pulse" />
          Paper trading • {snap.currency}
          <span className="hidden sm:inline">• {snap.positions.length} positions</span>
        </div>
        <h1 className="text-sm uppercase tracking-widest text-muted mb-2">
          Net Asset Value
        </h1>
        <div className="text-5xl sm:text-7xl font-semibold grad-text num leading-none">
          {sym}
          <CountUp value={snap.nav} decimals={2} />
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span
            className={`chip ${
              snap.totalReturnPct > 0
                ? "chip-good"
                : snap.totalReturnPct < 0
                ? "chip-bad"
                : "chip-muted"
            }`}
          >
            <span aria-hidden>{snap.totalReturnPct >= 0 ? "▲" : "▼"}</span>
            <span className="num">{percent(snap.totalReturnPct, 2)}</span>
            <span className="text-mutedDim">all time</span>
          </span>
          <span className="chip chip-muted num">
            <span className="text-mutedDim">Cash</span>
            <span>{sym}{snap.cash.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</span>
          </span>
          <span className="chip chip-muted num">
            <span className="text-mutedDim">Realized</span>
            <span className={snap.realizedPnl > 0 ? "text-good" : snap.realizedPnl < 0 ? "text-bad" : ""}>
              {snap.realizedPnl >= 0 ? "+" : "−"}
              {sym}
              {Math.abs(snap.realizedPnl).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </span>
          </span>
        </div>
        <div className="mt-6 text-xs text-mutedDim num">
          Last refresh {lastUpdate ? relativeTime(lastUpdate) : "—"}
        </div>
      </div>
    </motion.section>
  );
}
