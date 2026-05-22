"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { fetchState, placeholderSnapshot, type Snapshot } from "@/lib/state";
import { Topbar } from "@/components/Topbar";
import { HeroCard } from "@/components/HeroCard";
import { StatsRow } from "@/components/StatsRow";
import { AllocationDonut } from "@/components/AllocationDonut";
import { EquityCurve } from "@/components/EquityCurve";
import { PositionGrid } from "@/components/PositionGrid";
import { RecentTrades } from "@/components/RecentTrades";

export default function Dashboard() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await fetchState();
        if (!cancelled) {
          setSnap(s);
          setErr(null);
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "fetch failed");
          // Fall back to placeholder so the UI is never blank.
          setSnap((prev) => prev || placeholderSnapshot());
          setStale(true);
        }
      }
    };
    load();
    // Refresh every 5 minutes — the underlying state file only changes a few
    // times per day, so polling more often would be wasteful.
    const id = setInterval(load, 5 * 60 * 1000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  if (!snap) {
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="text-center">
          <div className="inline-block h-3 w-3 rounded-full bg-accent shimmer-bg mb-3" />
          <div className="text-sm text-muted">Loading paper trading state…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Topbar updatedAt={snap.updatedAt} snapshotAt={snap.snapshotAt} />

      {stale && err && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="glass rounded-xl p-3 text-xs text-muted"
        >
          State file fetch failed ({err}). Showing placeholder. If this persists,
          the daemon hasn&apos;t produced its first commit yet — trigger the workflow
          manually from GitHub Actions.
        </motion.div>
      )}

      <HeroCard snap={snap} />

      <StatsRow snap={snap} />

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <EquityCurve snap={snap} />
        </div>
        <div>
          <AllocationDonut snap={snap} />
        </div>
      </section>

      <PositionGrid snap={snap} />

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <RecentTrades snap={snap} />
        </div>
        <div className="glass rounded-2xl p-6">
          <h3 className="text-xs uppercase tracking-[0.18em] text-muted mb-4">About</h3>
          <p className="text-sm text-muted leading-relaxed">
            This dashboard is a static page. It reads{" "}
            <code className="px-1 bg-glass rounded text-xs">data/paper_state.json</code>{" "}
            directly from GitHub, which the daemon and snapshot workflows commit to the
            repo after each run.
          </p>
          <ul className="mt-4 text-sm text-muted space-y-2">
            <li>• Trade decisions: 3× per US/India market day</li>
            <li>• Snapshot refresh: 2× daily (incl weekends)</li>
            <li>• Currency: {snap.currency}</li>
            <li>
              • State commits:{" "}
              <a
                className="text-accent hover:underline"
                href="https://github.com/Architcybercrime/Stock-Market/commits/main/data/paper_state.json"
                target="_blank"
                rel="noopener noreferrer"
              >
                history →
              </a>
            </li>
          </ul>
        </div>
      </section>

      <footer className="text-center text-xs text-mutedDim pt-6 pb-2">
        Paper trading only. Not investment advice. Read{" "}
        <a
          className="hover:text-muted"
          href="https://github.com/Architcybercrime/Stock-Market/blob/main/docs/REALISTIC_EXPECTATIONS.md"
          target="_blank"
          rel="noopener noreferrer"
        >
          REALISTIC_EXPECTATIONS.md
        </a>{" "}
        before reading any of this as advice about the future.
      </footer>
    </div>
  );
}
