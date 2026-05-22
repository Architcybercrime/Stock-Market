"use client";

import useSWR from "swr";
import { useState } from "react";
import { apiFetch, getToken } from "@/lib/api";
import { Panel, Stat } from "@/components/Panel";

type RiskStatus = {
  kill_switch_engaged: boolean;
  kill_switch_reason: string;
  circuit_breaker_state: string;
  circuit_breaker_reason: string;
  limits: Record<string, number | string>;
};

export default function RiskPage() {
  const { data, mutate } = useSWR<RiskStatus>(
    getToken() ? "/api/v1/risk/status" : null,
    apiFetch,
    { refreshInterval: 3000 },
  );
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const post = async (path: string, body?: unknown) => {
    setBusy(true);
    setErr(null);
    try {
      await apiFetch(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      await mutate();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Panel title="Kill Switch">
          <Stat
            label="State"
            value={data?.kill_switch_engaged ? "ENGAGED" : "clear"}
            tone={data?.kill_switch_engaged ? "bad" : "good"}
          />
          {data?.kill_switch_engaged && data?.kill_switch_reason && (
            <p className="text-bad text-sm mt-2">{data.kill_switch_reason}</p>
          )}
          <div className="mt-4 space-y-2">
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="reason"
              className="w-full bg-bg border border-border rounded px-3 py-2 text-sm"
            />
            <div className="flex gap-2">
              <button
                disabled={busy || !reason}
                onClick={() => post("/api/v1/risk/kill", { reason })}
                className="rounded bg-bad px-3 py-2 text-white text-sm disabled:opacity-50"
              >
                Engage (operator)
              </button>
              <button
                disabled={busy || !data?.kill_switch_engaged}
                onClick={() => post("/api/v1/risk/release")}
                className="rounded bg-good px-3 py-2 text-white text-sm disabled:opacity-50"
              >
                Release (operator)
              </button>
            </div>
          </div>
        </Panel>

        <Panel title="Circuit Breaker">
          <Stat
            label="State"
            value={data?.circuit_breaker_state ?? "—"}
            tone={data?.circuit_breaker_state === "ok" ? "good" : "bad"}
          />
          {data?.circuit_breaker_reason && (
            <p className="text-muted text-sm mt-2">{data.circuit_breaker_reason}</p>
          )}
          <button
            disabled={busy || data?.circuit_breaker_state === "ok"}
            onClick={() => post("/api/v1/risk/reset-circuit-breaker")}
            className="mt-4 rounded bg-accent px-3 py-2 text-white text-sm disabled:opacity-50"
          >
            Reset (operator)
          </button>
        </Panel>
      </div>

      <Panel title="Limits">
        <pre className="text-xs text-muted overflow-auto">
          {JSON.stringify(data?.limits ?? {}, null, 2)}
        </pre>
      </Panel>

      {err && <p className="text-bad text-sm">{err}</p>}
    </div>
  );
}
