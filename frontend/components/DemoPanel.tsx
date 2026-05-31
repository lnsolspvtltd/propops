"use client";
import { useState } from "react";

const SCENARIOS = [
  { id: "emergency_leak", label: "🚨 Emergency Leak", urgency: "EMERGENCY" },
  { id: "lock_broken",    label: "🔒 Lock Broken",    urgency: "HIGH"      },
  { id: "noise_complaint",label: "📢 Noise Complaint", urgency: "MEDIUM"   },
  { id: "lease_question", label: "📋 Lease Query",    urgency: "LOW"       },
];

interface Props { onNewDraft: () => void }

export default function DemoPanel({ onNewDraft }: Props) {
  const [loading, setLoading] = useState<string | null>(null);
  const [result, setResult] = useState<{ urgency: string; ms: number } | null>(null);
  const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  async function simulate(scenario: string) {
    setLoading(scenario);
    setResult(null);
    try {
      const r = await fetch(`${API}/api/v1/demo/simulate-email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario }),
      });
      if (r.ok) {
        const d = await r.json();
        setResult({ urgency: d.urgency, ms: d.processing_time_ms });
        onNewDraft();
      }
    } catch { /* silent */ } finally {
      setLoading(null);
    }
  }

  if (process.env.NODE_ENV !== "development") return null;

  return (
    <div className="mx-4 mb-4 p-4 rounded-xl border border-dashed border-gray-700 bg-gray-900/50">
      <p className="text-xs font-semibold text-gray-400 mb-3">🎭 Demo Mode — Simulate incoming email</p>
      <div className="grid grid-cols-2 gap-2">
        {SCENARIOS.map((s) => (
          <button key={s.id} onClick={() => simulate(s.id)}
            disabled={!!loading}
            className="px-3 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-xs text-gray-300 text-left transition-colors">
            {loading === s.id ? "Processing…" : s.label}
          </button>
        ))}
      </div>
      {result && (
        <p className="mt-2 text-xs text-green-400">✓ {result.urgency} in {result.ms}ms</p>
      )}
    </div>
  );
}