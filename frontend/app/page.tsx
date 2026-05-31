"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { AlertCircle, RefreshCw, Mail, Clock, CheckCircle2, XCircle } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface PendingDraft {
  draft_id: string;
  incident_id: string;
  incident_title: string;
  urgency: "EMERGENCY" | "HIGH" | "MEDIUM" | "LOW";
  subject: string;
  body: string;
  recipient: string;
  created_at: string;
  raw_message?: string | null;
}

const URGENCY: Record<string, { queue: string; badge: string; dot: string }> = {
  EMERGENCY: { queue: "border-l-4 border-l-red-500", badge: "bg-red-600/20 text-red-400 border border-red-600/30", dot: "bg-red-500 animate-pulse" },
  HIGH:      { queue: "border-l-4 border-l-orange-400", badge: "bg-orange-500/20 text-orange-400 border border-orange-500/30", dot: "bg-orange-400" },
  MEDIUM:    { queue: "border-l-4 border-l-yellow-400", badge: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30", dot: "bg-yellow-400" },
  LOW:       { queue: "border-l-4 border-l-gray-500", badge: "bg-gray-700/50 text-gray-400 border border-gray-600/30", dot: "bg-gray-500" },
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function ApprovalQueue() {
  const [drafts, setDrafts] = useState<PendingDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PendingDraft | null>(null);
  const [activeTab, setActiveTab] = useState<"original" | "draft">("original");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetchDrafts = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    try {
      const res = await fetch(`${API}/api/v1/approvals/pending`, {
        signal: abortRef.current.signal,
        headers: { Accept: "application/json" },
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data: PendingDraft[] = await res.json();
      const sorted = [...data].sort((a, b) => {
        const order = { EMERGENCY: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
        return (order[a.urgency] ?? 9) - (order[b.urgency] ?? 9);
      });
      setDrafts(sorted);
      setError(null);
      if (!selected && sorted.length > 0) {
        setSelected(sorted[0]);
        setActiveTab("original");
      }
    } catch (e) {
      if (e instanceof Error && e.name !== "AbortError") {
        setError(e.message);
      }
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    fetchDrafts(true);
    timerRef.current = setInterval(() => fetchDrafts(false), 30_000);
    return () => {
      timerRef.current && clearInterval(timerRef.current);
      abortRef.current?.abort();
    };
  }, [fetchDrafts]);

  function showToast(msg: string, ok: boolean) {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  }

  async function handleApprove(draftId: string) {
    setActionLoading(draftId);
    const prev = drafts;
    setDrafts((d) => d.filter((x) => x.draft_id !== draftId));
    setSelected(null);
    try {
      const res = await fetch(`${API}/api/v1/approvals/${draftId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_by: "founder" }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      showToast("Reply sent successfully", true);
      fetchDrafts(false);
    } catch (e) {
      setDrafts(prev);
      showToast(`Approval failed: ${e instanceof Error ? e.message : "error"}`, false);
    } finally {
      setActionLoading(null);
    }
  }

  async function handleReject(draftId: string) {
    setActionLoading(draftId);
    const prev = drafts;
    setDrafts((d) => d.filter((x) => x.draft_id !== draftId));
    setSelected(null);
    try {
      const res = await fetch(`${API}/api/v1/approvals/${draftId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "rejected by property manager" }),
      });
      if (!res.ok) throw new Error(`Failed: ${res.status}`);
      showToast("Draft rejected", true);
      fetchDrafts(false);
    } catch (e) {
      setDrafts(prev);
      showToast(`Rejection failed: ${e instanceof Error ? e.message : "error"}`, false);
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="flex h-screen bg-gray-950 overflow-hidden">
      {/* Toast */}
      {toast && (
        <div className={`fixed top-4 right-4 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-xl text-sm font-medium ${toast.ok ? "bg-green-900 text-green-200 border border-green-700" : "bg-red-900 text-red-200 border border-red-700"}`}>
          {toast.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          {toast.msg}
        </div>
      )}

      {/* Left panel — queue */}
      <div className="w-80 flex-shrink-0 border-r border-gray-800 flex flex-col bg-gray-900">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-bold text-white text-lg">PropOps</h1>
              <p className="text-xs text-gray-400 mt-0.5">
                {drafts.length > 0 ? `${drafts.length} pending approval${drafts.length !== 1 ? "s" : ""}` : "All caught up"}
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => fetchDrafts(true)}
                className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-800 rounded transition-colors">
                <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
              </button>
              <Link href="/incidents"
                className="px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 rounded text-gray-300 transition-colors">
                Incidents ->
              </Link>
            </div>
          </div>
          {error && (
            <div className="mt-3 flex items-center gap-2 text-xs text-red-400 bg-red-950/30 rounded p-2">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" /> {error}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="p-4 border-b border-gray-800 animate-pulse">
                <div className="h-4 bg-gray-800 rounded w-3/4 mb-2" />
                <div className="h-3 bg-gray-800 rounded w-1/2" />
              </div>
            ))
          ) : drafts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-8">
              <div className="text-4xl mb-3">✅</div>
              <p className="text-gray-300 font-medium">All caught up!</p>
              <p className="text-gray-500 text-sm mt-1">No drafts waiting for approval.</p>
            </div>
          ) : (
            drafts.map((d) => (
              <button key={d.draft_id}
                onClick={() => { setSelected(d); setActiveTab("original"); }}
                className={`w-full text-left p-4 border-b border-gray-800 transition-all ${URGENCY[d.urgency]?.queue ?? ""} ${selected?.draft_id === d.draft_id ? "bg-gray-800" : "hover:bg-gray-800/50"}`}>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className={`text-xs px-1.5 py-0.5 rounded font-semibold ${URGENCY[d.urgency]?.badge ?? ""}`}>
                    {d.urgency}
                  </span>
                  <span className="text-xs text-gray-500 flex items-center gap-1">
                    <Clock className="w-3 h-3" />{timeAgo(d.created_at)}
                  </span>
                </div>
                <p className="text-sm text-white font-medium line-clamp-2 mt-1">{d.incident_title}</p>
                <p className="text-xs text-gray-500 mt-1 flex items-center gap-1">
                  <Mail className="w-3 h-3" />
                  <span className="truncate">{d.recipient}</span>
                </p>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right panel — detail */}
      {selected ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Header */}
          <div className="p-5 border-b border-gray-800 flex items-start justify-between bg-gray-900/50">
            <div>
              <h2 className="text-white font-semibold text-base">{selected.incident_title}</h2>
              <p className="text-xs text-gray-400 mt-1">To: {selected.recipient} · {timeAgo(selected.created_at)}</p>
            </div>
            <span className={`text-xs px-2 py-1 rounded font-bold ${URGENCY[selected.urgency]?.badge ?? ""}`}>
              {selected.urgency}
            </span>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-800 bg-gray-900/30">
            {(["original", "draft"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-5 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === tab ? "border-blue-500 text-blue-400" : "border-transparent text-gray-400 hover:text-gray-300"}`}>
                {tab === "original" ? "📧 Original Email" : "✍️ AI Draft"}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-5">
            {activeTab === "original" ? (
              <div>
                <div className="mb-3 text-xs text-gray-500 font-semibold uppercase tracking-wider">Tenant's original message</div>
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 text-gray-200 text-sm whitespace-pre-wrap leading-relaxed font-mono min-h-32">
                  {selected.raw_message || "(No original message available — email body was not captured)"}
                </div>
              </div>
            ) : (
              <div>
                <div className="mb-2 text-xs text-gray-500 font-semibold uppercase tracking-wider">AI-generated reply</div>
                <div className="mb-3 text-xs text-gray-400 font-medium">Subject: {selected.subject}</div>
                <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 text-gray-200 text-sm whitespace-pre-wrap leading-relaxed min-h-32">
                  {selected.body}
                </div>
              </div>
            )}
          </div>

          {/* Action bar */}
          <div className="p-5 border-t border-gray-800 bg-gray-900/50 flex gap-3">
            <button onClick={() => handleApprove(selected.draft_id)}
              disabled={!!actionLoading}
              className="flex-1 py-3 rounded-xl bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white font-semibold text-sm transition-colors flex items-center justify-center gap-2">
              <CheckCircle2 className="w-4 h-4" />
              {actionLoading === selected.draft_id ? "Sending…" : "Approve & Send"}
            </button>
            <button onClick={() => handleReject(selected.draft_id)}
              disabled={!!actionLoading}
              className="flex-1 py-3 rounded-xl bg-gray-800 hover:bg-red-950 disabled:opacity-50 text-gray-300 hover:text-red-300 font-semibold text-sm transition-colors flex items-center justify-center gap-2">
              <XCircle className="w-4 h-4" />
              Reject
            </button>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-gray-600">
          <div className="text-center">
            <div className="text-5xl mb-3">📬</div>
            <p className="text-gray-400">Select a draft to review</p>
          </div>
        </div>
      )}
    </div>
  );
}
