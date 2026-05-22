"use client";

import { motion } from "framer-motion";
import type { Snapshot } from "@/lib/state";
import { money, percent, symbolColor } from "@/lib/format";

export function PositionGrid({ snap }: { snap: Snapshot }) {
  if (snap.positions.length === 0) {
    return (
      <div className="glass rounded-2xl p-8 text-center">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted mb-3">Holdings</h3>
        <p className="text-sm text-muted max-w-md mx-auto">
          The system has not opened any positions yet. This happens when no signal clears
          the confidence threshold — usually on the first few runs or in choppy markets.
        </p>
      </div>
    );
  }

  return (
    <section>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted">
          Holdings ({snap.positions.length})
        </h3>
        <div className="text-xs text-muted">Sorted by market value</div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {snap.positions.map((p, i) => (
          <motion.div
            key={p.symbol}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.45,
              delay: 0.05 * i,
              ease: [0.22, 1, 0.36, 1],
            }}
            whileHover={{ y: -2, transition: { duration: 0.2 } }}
            className="glass rounded-2xl p-5 hover:glass-hi transition-colors relative overflow-hidden group"
          >
            {/* Background gradient bar indicating P&L */}
            <div
              className="absolute inset-x-0 bottom-0 h-1 transition-all"
              style={{
                background: p.unrealizedPct >= 0 ? "#10b981" : "#f43f5e",
                opacity: 0.6,
              }}
            />

            <div className="flex items-baseline justify-between mb-3">
              <div className="font-semibold text-text truncate">
                {p.symbol.replace(".NS", "").replace(".BO", "")}
              </div>
              <span
                className={`chip ${
                  p.unrealizedPct >= 0 ? "chip-good" : "chip-bad"
                } num`}
              >
                {percent(p.unrealizedPct, 2)}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-y-2 gap-x-3 text-xs">
              <div>
                <div className="text-mutedDim uppercase tracking-wider">Qty</div>
                <div className="num text-text">{p.qty.toLocaleString("en-IN")}</div>
              </div>
              <div>
                <div className="text-mutedDim uppercase tracking-wider">Weight</div>
                <div className="num text-text">{p.weight.toFixed(1)}%</div>
              </div>
              <div>
                <div className="text-mutedDim uppercase tracking-wider">Avg cost</div>
                <div className="num text-muted">{money(p.avgCost, snap.currency)}</div>
              </div>
              <div>
                <div className="text-mutedDim uppercase tracking-wider">Last</div>
                <div className="num text-text">{money(p.lastPrice, snap.currency)}</div>
              </div>
              <div className="col-span-2 pt-2 border-t border-border">
                <div className="text-mutedDim uppercase tracking-wider">Unrealized</div>
                <div className={`num text-sm ${symbolColor(p.unrealizedPnL)}`}>
                  {p.unrealizedPnL >= 0 ? "+" : "−"}
                  {money(Math.abs(p.unrealizedPnL), snap.currency)}
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
