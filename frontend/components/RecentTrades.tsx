"use client";

import { motion } from "framer-motion";
import type { Snapshot } from "@/lib/state";
import { money, relativeTime } from "@/lib/format";

export function RecentTrades({ snap }: { snap: Snapshot }) {
  const fills = [...snap.fills].sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 12);

  return (
    <div className="glass rounded-2xl p-6 h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs uppercase tracking-[0.18em] text-muted">Recent Trades</h3>
        <div className="text-xs text-muted num">{snap.fills.length} total</div>
      </div>
      {fills.length === 0 ? (
        <div className="py-6 text-center text-sm text-muted">
          No trades yet. The first fills will appear here.
        </div>
      ) : (
        <ul className="space-y-1.5">
          {fills.map((f, i) => {
            const qty = Number(f.qty);
            const price = Number(f.price);
            return (
              <motion.li
                key={f.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.35, delay: 0.04 * i }}
                className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-glass transition-colors"
              >
                <span
                  className={`chip ${
                    f.side === "buy" ? "chip-good" : "chip-bad"
                  } w-[44px] justify-center`}
                >
                  {f.side === "buy" ? "BUY" : "SELL"}
                </span>
                <span className="font-medium text-text flex-1 truncate">
                  {f.symbol.replace(".NS", "").replace(".BO", "")}
                </span>
                <span className="text-xs text-muted num shrink-0">
                  {qty.toLocaleString("en-IN")} @ {money(price, snap.currency)}
                </span>
                <span className="text-xs text-mutedDim w-[64px] text-right shrink-0">
                  {relativeTime(f.ts)}
                </span>
              </motion.li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
