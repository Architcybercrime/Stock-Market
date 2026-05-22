"use client";

import { motion } from "framer-motion";
import { relativeTime } from "@/lib/format";

export function Topbar({ updatedAt, snapshotAt }: { updatedAt?: string; snapshotAt?: string | null }) {
  const lastUpdate = snapshotAt || updatedAt || "";

  return (
    <motion.header
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="flex items-center justify-between mb-6 sm:mb-8"
    >
      <div className="flex items-center gap-3">
        <div className="relative h-8 w-8 rounded-lg overflow-hidden">
          <div
            className="absolute inset-0 animate-glow"
            style={{
              background:
                "conic-gradient(from 0deg, #6366f1, #22d3ee, #a78bfa, #6366f1)",
            }}
          />
          <div className="absolute inset-[3px] rounded-md bg-bg flex items-center justify-center text-xs font-semibold grad-text">
            SM
          </div>
        </div>
        <div>
          <div className="text-sm font-semibold tracking-wider">
            STOCK<span className="text-muted">_MARKET</span>
          </div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-mutedDim">
            Autonomous paper trading
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden sm:inline-flex items-center gap-2 text-xs text-muted px-3 py-1.5 rounded-full glass">
          <span className="inline-block h-2 w-2 rounded-full bg-good animate-pulse" />
          live • {lastUpdate ? relativeTime(lastUpdate) : "—"}
        </span>
        <a
          href="https://github.com/Architcybercrime/Stock-Market"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-muted hover:text-text transition-colors px-3 py-1.5 rounded-full glass hover:glass-hi"
        >
          GitHub →
        </a>
      </div>
    </motion.header>
  );
}
