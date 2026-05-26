"use client";

import { motion } from "framer-motion";
import type { Snapshot } from "@/lib/state";

/**
 * Indexed dual-line chart: your equity vs the benchmark, both normalized to
 * 100 at the first overlapping data point. Helps you see relative performance
 * without one dominating the scale.
 */
export function BenchmarkChart({ snap }: { snap: Snapshot }) {
  const eq = snap.equityHistory;
  const bench = snap.benchmarkHistory;
  if (eq.length < 2 || bench.length < 2) {
    return (
      <div className="glass rounded-2xl p-6 h-full flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs uppercase tracking-[0.18em] text-muted">
            You vs {snap.benchmarkSymbol}
          </h3>
        </div>
        <div className="flex-1 flex items-center justify-center text-sm text-muted">
          Not enough overlapping data yet. After a few snapshots both lines appear here.
        </div>
      </div>
    );
  }

  // Align both series on overlapping timestamps (take the last N where both exist).
  const N = Math.min(eq.length, bench.length, 120);
  const eqSlice = eq.slice(-N);
  const benchSlice = bench.slice(-N);

  // Index to 100 at the first overlap.
  const eqBase = eqSlice[0].value;
  const benchBase = benchSlice[0].value;
  const eqIdx = eqSlice.map((p) => (eqBase > 0 ? (p.value / eqBase) * 100 : 100));
  const benchIdx = benchSlice.map((p) => (benchBase > 0 ? (p.value / benchBase) * 100 : 100));

  const all = [...eqIdx, ...benchIdx];
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const W = 600;
  const H = 200;
  const PAD = 10;

  const toPath = (values: number[]) =>
    values
      .map((v, i) => {
        const x = PAD + (i / (values.length - 1)) * (W - PAD * 2);
        const y = H - PAD - ((v - min) / range) * (H - PAD * 2);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");

  const eqPath = toPath(eqIdx);
  const benchPath = toPath(benchIdx);

  const eqReturn = eqIdx[eqIdx.length - 1] - 100;
  const benchReturn = benchIdx[benchIdx.length - 1] - 100;
  const alpha = eqReturn - benchReturn;

  return (
    <div className="glass rounded-2xl p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted">
          You vs {snap.benchmarkSymbol}
        </h3>
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-accent" />
            <span className="text-muted">You</span>
            <span className={`num ${eqReturn >= 0 ? "text-good" : "text-bad"}`}>
              {eqReturn >= 0 ? "+" : "−"}
              {Math.abs(eqReturn).toFixed(2)}%
            </span>
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full bg-muted" />
            <span className="text-muted">{snap.benchmarkSymbol}</span>
            <span className={`num ${benchReturn >= 0 ? "text-good" : "text-bad"}`}>
              {benchReturn >= 0 ? "+" : "−"}
              {Math.abs(benchReturn).toFixed(2)}%
            </span>
          </span>
        </div>
      </div>
      <div className="flex-1">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
          <defs>
            <linearGradient id="bench-eq-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.18" />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity="0" />
            </linearGradient>
          </defs>
          {/* baseline at 100 */}
          {(() => {
            const yBaseline = H - PAD - ((100 - min) / range) * (H - PAD * 2);
            return (
              <line
                x1={PAD}
                y1={yBaseline}
                x2={W - PAD}
                y2={yBaseline}
                stroke="rgba(255,255,255,0.07)"
                strokeDasharray="3 3"
              />
            );
          })()}
          <motion.path
            d={benchPath}
            fill="none"
            stroke="#8c93a3"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.0 }}
          />
          <motion.path
            d={eqPath + ` L ${W - PAD} ${H - PAD} L ${PAD} ${H - PAD} Z`}
            fill="url(#bench-eq-fill)"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.2, delay: 0.2 }}
          />
          <motion.path
            d={eqPath}
            fill="none"
            stroke="#22d3ee"
            strokeWidth={2}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
          />
        </svg>
      </div>
      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-muted num">indexed to 100 at start of window</span>
        <span className={`num font-medium ${alpha >= 0 ? "text-good" : "text-bad"}`}>
          α {alpha >= 0 ? "+" : "−"}
          {Math.abs(alpha).toFixed(2)}%
        </span>
      </div>
    </div>
  );
}
