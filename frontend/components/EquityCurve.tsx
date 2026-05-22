"use client";

import { motion } from "framer-motion";
import type { Snapshot } from "@/lib/state";
import { moneyCompact } from "@/lib/format";

export function EquityCurve({ snap }: { snap: Snapshot }) {
  const series = snap.equityHistory;
  if (series.length < 2) {
    return (
      <div className="glass rounded-2xl p-6 h-full flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xs uppercase tracking-[0.18em] text-muted">Equity Curve</h3>
        </div>
        <div className="flex-1 flex items-center justify-center text-sm text-muted">
          Not enough data yet. After a few snapshots the chart appears here.
        </div>
      </div>
    );
  }

  // Take at most the last 90 points for visual clarity
  const points = series.slice(-90);
  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 600;
  const H = 180;
  const PAD = 8;

  const path = points
    .map((p, i) => {
      const x = PAD + (i / (points.length - 1)) * (W - PAD * 2);
      const y = H - PAD - ((p.value - min) / range) * (H - PAD * 2);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const areaPath = `${path} L ${W - PAD} ${H - PAD} L ${PAD} ${H - PAD} Z`;

  const first = values[0];
  const last = values[values.length - 1];
  const changePct = first > 0 ? ((last - first) / first) * 100 : 0;
  const positive = changePct >= 0;
  const lineColor = positive ? "#10b981" : "#f43f5e";
  const fillColor = positive ? "rgba(16,185,129,0.15)" : "rgba(244,63,94,0.15)";

  return (
    <div className="glass rounded-2xl p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted">Equity Curve</h3>
        <div className="text-xs text-muted num">
          {points.length} samples • {moneyCompact(min, snap.currency)} – {moneyCompact(max, snap.currency)}
        </div>
      </div>
      <div className="flex-1">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full">
          <defs>
            <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={lineColor} stopOpacity="0.35" />
              <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
            </linearGradient>
          </defs>
          <motion.path
            d={areaPath}
            fill="url(#equity-fill)"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 1.1, delay: 0.2 }}
          />
          <motion.path
            d={path}
            fill="none"
            stroke={lineColor}
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
          />
        </svg>
      </div>
      <div className="mt-2 flex items-center justify-between">
        <div className="text-xs text-muted num">{points[0].ts.slice(0, 10)}</div>
        <div className={`text-sm font-medium num ${positive ? "text-good" : "text-bad"}`}>
          {positive ? "+" : "−"}{Math.abs(changePct).toFixed(2)}%
        </div>
        <div className="text-xs text-muted num">{points[points.length - 1].ts.slice(0, 10)}</div>
      </div>
    </div>
  );
}
