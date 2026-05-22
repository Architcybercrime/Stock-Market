"use client";

import { motion } from "framer-motion";
import type { Snapshot } from "@/lib/state";

const PALETTE = [
  "#6366f1", "#22d3ee", "#a78bfa", "#f472b6", "#34d399",
  "#fb923c", "#facc15", "#60a5fa", "#f87171", "#5eead4",
  "#c084fc", "#fbbf24",
];

interface Slice {
  symbol: string;
  weight: number;   // fraction of NAV (0..1)
  color: string;
}

export function AllocationDonut({ snap }: { snap: Snapshot }) {
  const totalNav = Math.max(snap.nav, 1);
  const slices: Slice[] = snap.positions.slice(0, PALETTE.length).map((p, i) => ({
    symbol: p.symbol.replace(".NS", "").replace(".BO", ""),
    weight: Math.max(0, p.marketValue / totalNav),
    color: PALETTE[i % PALETTE.length],
  }));
  const positionsWeight = slices.reduce((s, x) => s + x.weight, 0);
  const cashWeight = Math.max(0, 1 - positionsWeight);
  if (cashWeight > 0.001) {
    slices.push({ symbol: "Cash", weight: cashWeight, color: "#3b3f4a" });
  }

  // SVG donut math
  const R = 70;
  const STROKE = 22;
  const C = 2 * Math.PI * R;
  let offset = 0;

  return (
    <div className="glass rounded-2xl p-6 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted">Allocation</h3>
        <div className="text-xs text-muted">{snap.positions.length} positions</div>
      </div>

      <div className="flex flex-col lg:flex-row items-center gap-5">
        {/* Donut */}
        <div className="relative shrink-0">
          <svg width="180" height="180" viewBox="-90 -90 180 180" className="-rotate-90">
            {/* track */}
            <circle r={R} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={STROKE} />
            {slices.map((s, i) => {
              const len = s.weight * C;
              const dash = `${len} ${C - len}`;
              const dashoffset = -offset;
              offset += len;
              return (
                <motion.circle
                  key={s.symbol}
                  r={R}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={STROKE}
                  strokeDasharray={dash}
                  strokeDashoffset={dashoffset}
                  strokeLinecap="butt"
                  initial={{ opacity: 0, strokeWidth: 0 }}
                  animate={{ opacity: 1, strokeWidth: STROKE }}
                  transition={{
                    duration: 0.6,
                    delay: 0.15 + i * 0.05,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                />
              );
            })}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <div className="text-[10px] uppercase tracking-widest text-muted">Invested</div>
            <div className="text-xl font-semibold num">
              {(positionsWeight * 100).toFixed(1)}%
            </div>
          </div>
        </div>

        {/* Legend */}
        <div className="flex-1 w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-1.5 max-h-[210px] overflow-y-auto pr-1">
          {slices.map((s, i) => (
            <motion.div
              key={s.symbol}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.4, delay: 0.2 + i * 0.03 }}
              className="flex items-center justify-between gap-3 text-sm py-1 px-2 rounded hover:bg-glass"
            >
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm shrink-0"
                  style={{ background: s.color }}
                />
                <span className="truncate text-text">{s.symbol}</span>
              </span>
              <span className="num text-muted shrink-0">
                {(s.weight * 100).toFixed(1)}%
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
