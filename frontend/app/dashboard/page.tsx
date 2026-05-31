"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface DashboardStats {
  open_incidents: number;
  awaiting_approval: number;
  resolved_this_week: number;
  avg_response_hours: number;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await apiFetch("/api/v1/dashboard/stats");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        setStats(await res.json());
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load stats");
      }
    })();
  }, []);

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-xl font-semibold text-white">Dashboard</h1>
      {error && <p className="text-sm text-red-400">{error}</p>}
      {!stats && !error && <p className="text-sm text-gray-500">Loading…</p>}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[
            { label: "Open incidents", value: stats.open_incidents },
            { label: "Awaiting approval", value: stats.awaiting_approval },
            { label: "Resolved this week", value: stats.resolved_this_week },
            { label: "Avg response (h)", value: stats.avg_response_hours.toFixed(1) },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <p className="text-xs text-gray-500">{c.label}</p>
              <p className="text-2xl font-semibold text-white mt-1">{c.value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
