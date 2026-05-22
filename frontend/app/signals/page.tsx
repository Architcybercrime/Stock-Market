"use client";

import useSWR from "swr";
import { apiFetch, getToken } from "@/lib/api";
import { Panel } from "@/components/Panel";

type Signal = {
  id: string;
  symbol: string;
  ts: string;
  direction: string;
  target_weight: number;
  confidence: number;
  horizon_bars: number;
  model_id: string;
  model_version: string;
  rationale: string;
};

export default function SignalsPage() {
  const { data } = useSWR<Signal[]>(
    getToken() ? "/api/v1/signals/" : null,
    apiFetch,
    { refreshInterval: 5000 },
  );

  return (
    <Panel title="Latest signals" subtitle={`${data?.length ?? 0} shown`}>
      {!data || data.length === 0 ? (
        <p className="text-muted text-sm">No signals yet.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-muted text-left">
            <tr>
              <th className="py-2">Symbol</th>
              <th>Dir</th>
              <th>Weight</th>
              <th>Conf</th>
              <th>Model</th>
              <th>Rationale</th>
            </tr>
          </thead>
          <tbody>
            {data.map((s) => (
              <tr key={s.id} className="border-t border-border">
                <td className="py-2">{s.symbol}</td>
                <td
                  className={
                    s.direction === "long"
                      ? "text-good"
                      : s.direction === "short"
                      ? "text-bad"
                      : "text-muted"
                  }
                >
                  {s.direction}
                </td>
                <td>{s.target_weight.toFixed(3)}</td>
                <td>{(s.confidence * 100).toFixed(0)}%</td>
                <td className="text-muted">{s.model_id}@{s.model_version}</td>
                <td className="text-muted text-xs">{s.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
