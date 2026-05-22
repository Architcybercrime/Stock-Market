"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { apiFetch, getToken, login } from "@/lib/api";
import { Panel, Stat } from "@/components/Panel";

type PortfolioView = {
  nav: string;
  cash: string;
  initial_capital: string;
  realized_pnl: string;
  unrealized_pnl: string;
  positions: Array<{
    symbol: string;
    qty: string;
    avg_cost: string;
    unrealized_pnl: string;
    realized_pnl: string;
  }>;
};

type RiskStatus = {
  kill_switch_engaged: boolean;
  kill_switch_reason: string;
  circuit_breaker_state: string;
  circuit_breaker_reason: string;
  limits: Record<string, number | string>;
};

export default function Dashboard() {
  const [authed, setAuthed] = useState<boolean>(false);

  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  const { data: portfolio } = useSWR<PortfolioView>(
    authed ? "/api/v1/portfolio/" : null,
    apiFetch,
    { refreshInterval: 5000 },
  );
  const { data: risk } = useSWR<RiskStatus>(
    authed ? "/api/v1/risk/status" : null,
    apiFetch,
    { refreshInterval: 5000 },
  );

  if (!authed) {
    return <LoginCard onAuthed={() => setAuthed(true)} />;
  }

  const nav = Number(portfolio?.nav ?? 0);
  const realized = Number(portfolio?.realized_pnl ?? 0);
  const unrealized = Number(portfolio?.unrealized_pnl ?? 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Panel title="NAV">
          <Stat label="Total" value={`$${nav.toLocaleString()}`} />
        </Panel>
        <Panel title="Realized P&L">
          <Stat
            label="To-date"
            value={`$${realized.toFixed(2)}`}
            tone={realized > 0 ? "good" : realized < 0 ? "bad" : "neutral"}
          />
        </Panel>
        <Panel title="Unrealized P&L">
          <Stat
            label="Mark-to-market"
            value={`$${unrealized.toFixed(2)}`}
            tone={unrealized > 0 ? "good" : unrealized < 0 ? "bad" : "neutral"}
          />
        </Panel>
        <Panel title="Risk">
          <Stat
            label="Kill switch"
            value={risk?.kill_switch_engaged ? "ENGAGED" : "clear"}
            tone={risk?.kill_switch_engaged ? "bad" : "good"}
          />
          <div className="mt-3 text-xs text-muted">
            Circuit: <span className="text-text">{risk?.circuit_breaker_state ?? "—"}</span>
          </div>
        </Panel>
      </div>

      <Panel title="Positions" subtitle={`${portfolio?.positions.length ?? 0} open`}>
        {portfolio?.positions.length ? (
          <table className="w-full text-sm">
            <thead className="text-muted text-left">
              <tr>
                <th className="py-2">Symbol</th>
                <th>Qty</th>
                <th>Avg Cost</th>
                <th>Unrealized</th>
                <th>Realized</th>
              </tr>
            </thead>
            <tbody>
              {portfolio.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-border">
                  <td className="py-2">{p.symbol}</td>
                  <td>{p.qty}</td>
                  <td>${Number(p.avg_cost).toFixed(2)}</td>
                  <td>${Number(p.unrealized_pnl).toFixed(2)}</td>
                  <td>${Number(p.realized_pnl).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-muted text-sm">No open positions.</p>
        )}
      </Panel>

      <Panel title="Risk limits">
        <pre className="text-xs text-muted overflow-auto">
          {JSON.stringify(risk?.limits ?? {}, null, 2)}
        </pre>
      </Panel>
    </div>
  );
}

function LoginCard({ onAuthed }: { onAuthed: () => void }) {
  const [u, setU] = useState("viewer");
  const [p, setP] = useState("viewer");
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      await login(u, p);
      onAuthed();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "login failed");
    }
  };

  return (
    <div className="max-w-sm mx-auto">
      <Panel title="Login" subtitle="default scaffold creds">
        <form onSubmit={submit} className="space-y-3 text-sm">
          <label className="block">
            <span className="block text-muted mb-1">Username</span>
            <input
              value={u}
              onChange={(e) => setU(e.target.value)}
              className="w-full bg-bg border border-border rounded px-3 py-2"
            />
          </label>
          <label className="block">
            <span className="block text-muted mb-1">Password</span>
            <input
              type="password"
              value={p}
              onChange={(e) => setP(e.target.value)}
              className="w-full bg-bg border border-border rounded px-3 py-2"
            />
          </label>
          <button
            type="submit"
            className="w-full rounded bg-accent px-3 py-2 text-white font-medium"
          >
            Sign in
          </button>
          {err && <p className="text-bad text-xs">{err}</p>}
          <p className="text-xs text-muted">
            Defaults: viewer/viewer or operator/operator. Change before any deploy.
          </p>
        </form>
      </Panel>
    </div>
  );
}
