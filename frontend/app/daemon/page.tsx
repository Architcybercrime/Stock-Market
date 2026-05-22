"use client";

import useSWR from "swr";
import { apiFetch, getToken } from "@/lib/api";
import { Panel, Stat } from "@/components/Panel";

type PortfolioView = {
  nav: string;
  cash: string;
  positions: Array<{ symbol: string; qty: string; avg_cost: string; unrealized_pnl: string }>;
};

type RiskStatus = {
  kill_switch_engaged: boolean;
  circuit_breaker_state: string;
};

export default function DaemonPage() {
  const { data: portfolio } = useSWR<PortfolioView>(
    getToken() ? "/api/v1/portfolio/" : null,
    apiFetch,
    { refreshInterval: 10000 },
  );
  const { data: risk } = useSWR<RiskStatus>(
    getToken() ? "/api/v1/risk/status" : null,
    apiFetch,
    { refreshInterval: 10000 },
  );

  return (
    <div className="space-y-6">
      <Panel
        title="Daemon"
        subtitle="autonomous paper trader"
      >
        <p className="text-sm text-muted">
          The daemon runs locally via{" "}
          <code className="text-text">python scripts/run_daemon.py</code>. It picks
          a risk profile at startup, then trades once per US market close. This
          page shows the broker-side state — positions, P&amp;L, risk gates — so
          you can watch what the daemon has been doing.
        </p>
        <p className="text-sm text-muted mt-2">
          Don&apos;t expect activity outside market hours. The daemon is paper-only
          by default and will refuse to switch to live until the explicit flags in{" "}
          <code className="text-text">.env</code> are flipped.
        </p>
      </Panel>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Panel title="NAV">
          <Stat label="Total" value={`$${Number(portfolio?.nav ?? 0).toLocaleString()}`} />
        </Panel>
        <Panel title="Cash">
          <Stat label="Available" value={`$${Number(portfolio?.cash ?? 0).toLocaleString()}`} />
        </Panel>
        <Panel title="Safety">
          <Stat
            label="Kill switch"
            value={risk?.kill_switch_engaged ? "ENGAGED" : "clear"}
            tone={risk?.kill_switch_engaged ? "bad" : "good"}
          />
          <div className="mt-3 text-xs text-muted">
            Breaker: <span className="text-text">{risk?.circuit_breaker_state ?? "—"}</span>
          </div>
        </Panel>
      </div>

      <Panel title="Holdings" subtitle={`${portfolio?.positions.length ?? 0} positions`}>
        {!portfolio?.positions.length ? (
          <p className="text-muted text-sm">
            No open positions. The daemon is either waiting for its next run, or its
            signals didn&apos;t clear the confidence threshold today.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-muted text-left">
              <tr>
                <th className="py-2">Symbol</th>
                <th>Qty</th>
                <th>Avg cost</th>
                <th>Unrealized</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-border">
                  <td className="py-2">{p.symbol}</td>
                  <td>{p.qty}</td>
                  <td>${Number(p.avg_cost).toFixed(2)}</td>
                  <td>${Number(p.unrealized_pnl).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
