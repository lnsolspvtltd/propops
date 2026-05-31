"use client";
import { useEffect, useState } from "react";

interface CategoryCount { category: string; count: number }
interface RecentIncident {
  id: string; subject: string; tenant_name: string | null;
  unit_label: string | null; urgency: string | null;
  status: string; created_at: string;
}
interface Stats {
  open_incidents: number; awaiting_approval: number;
  resolved_this_week: number; avg_response_hours: number;
  top_categories: CategoryCount[]; recent_incidents: RecentIncident[];
}

const URGENCY_COLOR: Record<string, string> = {
  EMERGENCY: "bg-red-600", HIGH: "bg-orange-500",
  MEDIUM: "bg-yellow-500", LOW: "bg-gray-500",
};

function StatCard({ label, value, unit = "", highlight = false }:
  { label: string; value: number; unit?: string; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border p-5 ${highlight && value > 0
      ? "border-red-700 bg-red-950/30" : "border-gray-800 bg-gray-900"}`}>
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-3xl font-bold text-white">
        {value}{unit && <span className="text-lg text-gray-400 ml-1">{unit}</span>}
      </p>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      const r = await fetch("/api/v1/dashboard/stats");
      if (r.ok) setStats(await r.json());
    } catch { /* silent — show stale data */ } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="text-gray-500 text-sm">Loading...</div>;
  if (!stats) return <div className="text-red-400 text-sm">Failed to load stats.</div>;

  const maxCat = Math.max(...stats.top_categories.map((c) => c.count), 1);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Open Incidents" value={stats.open_incidents} highlight={stats.open_incidents > 10} />
        <StatCard label="Awaiting Reply" value={stats.awaiting_approval} highlight={stats.awaiting_approval > 0} />
        <StatCard label="Resolved This Week" value={stats.resolved_this_week} />
        <StatCard label="Avg Response" value={stats.avg_response_hours} unit="hrs" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Recent incidents */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-300">Recent Open Incidents</h2>
            <a href="/incidents" className="text-xs text-blue-400 hover:text-blue-300">View all →</a>
          </div>
          {stats.recent_incidents.length === 0
            ? <p className="text-gray-500 text-sm">No open incidents.</p>
            : <ul className="space-y-3">
              {stats.recent_incidents.map((i) => (
                <li key={i.id} className="flex items-start gap-3">
                  <span className={`mt-0.5 h-2 w-2 rounded-full flex-shrink-0 ${URGENCY_COLOR[i.urgency ?? ""] ?? "bg-gray-600"}`} />
                  <div className="min-w-0">
                    <p className="text-sm text-white truncate">{i.subject}</p>
                    <p className="text-xs text-gray-400">{i.tenant_name ?? "Unknown"} · {i.unit_label ?? "—"}</p>
                  </div>
                </li>
              ))}
            </ul>
          }
        </div>

        {/* Top categories */}
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="text-sm font-semibold text-gray-300 mb-4">Top Issue Types</h2>
          {stats.top_categories.length === 0
            ? <p className="text-gray-500 text-sm">No data yet.</p>
            : <ul className="space-y-3">
              {stats.top_categories.map((c) => (
                <li key={c.category}>
                  <div className="flex justify-between text-xs text-gray-400 mb-1">
                    <span className="capitalize">{c.category}</span>
                    <span>{c.count}</span>
                  </div>
                  <div className="h-2 rounded bg-gray-800">
                    <div className="h-2 rounded bg-blue-500 transition-all"
                      style={{ width: `${(c.count / maxCat) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          }
        </div>
      </div>
    </div>
  );
}