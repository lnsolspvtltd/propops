"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

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
  const searchParams = useSearchParams();
  const focusId = searchParams.get("focus");

  const [drafts, setDrafts] = useState<PendingDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PendingDraft | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchDrafts = async () => {
    try {
      const res = await fetch(`${API}/api/v1/approvals/pending`);
      const data = await res.json();
      setDrafts(data);
      if (focusId) {
        const draft = data.find((d: PendingDraft) => d.draft_id === focusId);
        if (draft) setSelected(draft);
      } else if (data.length > 0 && !selected) {
        setSelected(data[0]);
      }
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
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-950/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">PropOps</h1>
            <p className="text-gray-400 mt-1 text-sm">AI Approval Queue</p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-gray-400 text-sm">
              {drafts.length} pending approval{drafts.length !== 1 ? "s" : ""}
            </span>
            <button 
              onClick={fetchDrafts}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors text-gray-300 font-medium"
            >
              Refresh
            </button>
            <Link
              href="/incidents"
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-sm transition-colors text-white font-medium"
            >
              View All →
            </Link>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-6xl mx-auto px-4 py-8">
        {loading ? (
          <div className="text-center text-gray-400 py-20">Loading...</div>
        ) : drafts.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-6xl mb-4">✅</div>
            <p className="text-xl text-gray-300">All caught up!</p>
            <p className="text-gray-500 mt-2">No drafts waiting for approval.</p>
            <Link href="/incidents" className="mt-6 inline-block px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-white font-medium transition-colors">
              View all incidents
            </Link>
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