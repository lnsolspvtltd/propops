"use client";
import { useState, useEffect } from "react";

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
}

const urgencyColors: Record<string, string> = {
  EMERGENCY: "bg-red-600 text-white",
  HIGH: "bg-orange-500 text-white",
  MEDIUM: "bg-yellow-500 text-gray-900",
  LOW: "bg-green-600 text-white",
};

export default function ApprovalQueue() {
  const [drafts, setDrafts] = useState<PendingDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PendingDraft | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchDrafts = async () => {
    try {
      const res = await fetch(`${API}/api/v1/approvals/pending`);
      const data = await res.json();
      setDrafts(data);
    } catch (e) {
      console.error("Failed to fetch drafts", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDrafts();
    const interval = setInterval(fetchDrafts, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleApprove = async (draftId: string) => {
    setActionLoading(draftId);
    await fetch(`${API}/api/v1/approvals/${draftId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ approved_by: "founder" }),
    });
    setDrafts(prev => prev.filter(d => d.draft_id !== draftId));
    setSelected(null);
    setActionLoading(null);
  };

  const handleReject = async (draftId: string) => {
    setActionLoading(draftId);
    await fetch(`${API}/api/v1/approvals/${draftId}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "manual rejection" }),
    });
    setDrafts(prev => prev.filter(d => d.draft_id !== draftId));
    setSelected(null);
    setActionLoading(null);
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">PropOps</h1>
          <p className="text-gray-400 mt-1">AI Approval Queue</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-gray-400 text-sm">
            {drafts.length} pending approval{drafts.length !== 1 ? "s" : ""}
          </span>
          <button onClick={fetchDrafts}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors">
            Refresh
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-center text-gray-400 py-20">Loading...</div>
      ) : drafts.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-6xl mb-4">✅</div>
          <p className="text-xl text-gray-300">All caught up!</p>
          <p className="text-gray-500 mt-2">No drafts waiting for approval.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Draft list */}
          <div className="space-y-3">
            {drafts.map(draft => (
              <div key={draft.draft_id}
                onClick={() => setSelected(draft)}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  selected?.draft_id === draft.draft_id
                    ? "border-blue-500 bg-blue-950/30"
                    : "border-gray-800 bg-gray-900 hover:border-gray-600"
                }`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-white text-sm truncate">{draft.incident_title}</p>
                    <p className="text-gray-400 text-xs mt-1 truncate">{draft.recipient}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded font-medium shrink-0 ${urgencyColors[draft.urgency]}`}>
                    {draft.urgency}
                  </span>
                </div>
                <p className="text-gray-500 text-xs mt-2 truncate">{draft.subject}</p>
              </div>
            ))}
          </div>

          {/* Draft detail */}
          {selected && (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 sticky top-4">
              <div className="flex items-center justify-between mb-4">
                <span className={`text-xs px-2 py-1 rounded font-medium ${urgencyColors[selected.urgency]}`}>
                  {selected.urgency}
                </span>
                <button onClick={() => setSelected(null)} className="text-gray-500 hover:text-gray-300 text-xl">×</button>
              </div>
              <h2 className="text-white font-semibold mb-1">{selected.incident_title}</h2>
              <p className="text-gray-400 text-sm mb-4">To: {selected.recipient}</p>

              <div className="bg-gray-950 rounded p-4 mb-4">
                <p className="text-gray-300 text-xs font-mono font-semibold mb-2">SUBJECT: {selected.subject}</p>
                <hr className="border-gray-800 mb-3" />
                <p className="text-gray-200 text-sm whitespace-pre-wrap leading-relaxed">{selected.body}</p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => handleApprove(selected.draft_id)}
                  disabled={actionLoading === selected.draft_id}
                  className="flex-1 py-2.5 bg-green-600 hover:bg-green-500 disabled:opacity-50 rounded text-white text-sm font-medium transition-colors">
                  {actionLoading === selected.draft_id ? "..." : "✓ Approve & Send"}
                </button>
                <button
                  onClick={() => handleReject(selected.draft_id)}
                  disabled={actionLoading === selected.draft_id}
                  className="flex-1 py-2.5 bg-gray-800 hover:bg-red-900 disabled:opacity-50 rounded text-white text-sm font-medium transition-colors">
                  ✕ Reject
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
