"use client";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

const SCENARIOS = [
  { id: "emergency_leak", label: "🚨 Emergency Leak", urgency: "EMERGENCY" },
  { id: "lock_broken", label: "🔒 Lock Broken", urgency: "HIGH" },
  { id: "noise_complaint", label: "📢 Noise Complaint", urgency: "MEDIUM" },
  { id: "lease_question", label: "📋 Lease Query", urgency: "LOW" },
];

export interface SimulateResult {
  draft_id: string;
  urgency: string;
  processing_time_ms: number;
}

interface Props {
  onNewDraft: (result: SimulateResult) => void;
}

export default function DemoPanel({ onNewDraft }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function simulate(scenario: string) {
    setLoading(scenario);
    setError(null);
    try {
      const r = await apiFetch("/api/v1/demo/simulate-email", {
        method: "POST",
        body: JSON.stringify({ scenario }),
      });
      if (!r.ok) {
        const msg = `Simulation failed (${r.status})`;
        setError(msg);
        console.error(msg);
        return;
      }
      const d = await r.json();
      onNewDraft({
        draft_id: d.draft_id,
        urgency: d.urgency,
        processing_time_ms: d.processing_time_ms,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Simulation failed";
      setError(msg);
      console.error("Demo simulate error:", e);
    } finally {
      setLoading(null);
    }
  }

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <div className="mx-3 mb-3 p-3 rounded-xl border border-dashed border-gray-700 bg-gray-900/50">
      <p className="text-xs font-semibold text-gray-400 mb-2">🎭 Demo Mode</p>
      <p className="text-[10px] text-gray-500 mb-2">Simulate an incoming email through the AI pipeline</p>
      {error && (
        <p className="text-[10px] text-red-400 mb-2" role="alert">{error}</p>
      )}
      {loading && (
        <div className="mb-2 h-1.5 w-full rounded-full bg-gray-800 overflow-hidden">
          <div className="h-full w-2/3 bg-blue-500 animate-pulse rounded-full" />
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => simulate(s.id)}
            disabled={!!loading}
            className="px-2 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-xs text-gray-300 text-left transition-colors"
          >
            {loading === s.id ? "Processing…" : s.label}
          </button>
        ))}
      </div>
    </div>
  );
}
