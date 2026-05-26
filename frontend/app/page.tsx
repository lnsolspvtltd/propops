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

interface FetchError {
  message: string;
  timestamp: string;
}

const urgencyConfig = {
  EMERGENCY: {
    color: "bg-red-600 hover:bg-red-700 text-white",
    badge: "bg-red-600/20 text-red-400 border-red-600/30",
    order: 0,
    icon: "🚨",
  },
  HIGH: {
    color: "bg-orange-500 hover:bg-orange-600 text-white",
    badge: "bg-orange-500/20 text-orange-400 border-orange-500/30",
    order: 1,
    icon: "⚠️",
  },
  MEDIUM: {
    color: "bg-yellow-500 hover:bg-yellow-600 text-gray-900",
    badge: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    order: 2,
    icon: "📋",
  },
  LOW: {
    color: "bg-green-600 hover:bg-green-700 text-white",
    badge: "bg-green-600/20 text-green-400 border-green-600/30",
    order: 3,
    icon: "ℹ️",
  },
};

// SECURITY-REVIEW: API calls use fetch with proper error handling, no sensitive data in logs
function DraftSkeleton() {
  return (
    <div className="p-4 rounded-lg border border-gray-800 bg-gray-900 animate-pulse">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <div className="h-4 bg-gray-800 rounded w-3/4"></div>
          <div className="h-3 bg-gray-800 rounded w-1/2 mt-2"></div>
        </div>
        <div className="h-6 bg-gray-800 rounded w-16"></div>
      </div>
    </div>
  );
}

function ErrorBanner({ error, onDismiss }: { error: FetchError; onDismiss: () => void }) {
  return (
    <div className="mb-6 p-4 bg-red-950/50 border border-red-800 rounded-lg flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-red-300 font-medium text-sm">Error loading drafts</p>
        <p className="text-red-400 text-xs mt-1">{error.message}</p>
        <p className="text-red-500/60 text-xs mt-1">{error.timestamp}</p>
      </div>
      <button
        onClick={onDismiss}
        className="text-red-400 hover:text-red-300 text-lg flex-shrink-0"
      >
        ×
      </button>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-20">
      <div className="text-6xl mb-4 animate-bounce">✅</div>
      <p className="text-xl text-gray-300 font-medium">All caught up!</p>
      <p className="text-gray-500 mt-2">No drafts waiting for approval.</p>
    </div>
  );
}

export default function ApprovalQueue() {
  const searchParams = useSearchParams();
  const focusId = searchParams.get("focus");

  const [drafts, setDrafts] = useState<PendingDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<PendingDraft | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<FetchError | null>(null);
  const [lastRefresh, setLastRefresh] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const fetchDrafts = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true);
    abortControllerRef.current = new AbortController();

    try {
      const res = await fetch(`${API}/api/v1/approvals/pending`, {
        signal: abortControllerRef.current.signal,
        headers: { "Accept": "application/json" },
      });

      if (!res.ok) {
        throw new Error(
          res.status === 404
            ? "Approval endpoint not found"
            : `Server error: ${res.status}`
        );
      }

      const data = await res.json();
      setDrafts(data);
      if (focusId) {
        const draft = data.find((d: PendingDraft) => d.draft_id === focusId);
        if (draft) setSelected(draft);
      } else if (data.length > 0 && !selected) {
        setSelected(data[0]);
      }
    } catch (e) {
      if (e instanceof Error && e.name !== "AbortError") {
        console.error("Failed to fetch drafts:", e);
        setError({
          message: e.message || "Failed to load drafts. Please try again.",
          timestamp: new Date().toLocaleTimeString(),
        });
      }
    } finally {
      setLoading(false);
    }
  }, [selected]);

  // Setup auto-refresh polling
  useEffect(() => {
    fetchDrafts(true);

    pollIntervalRef.current = setInterval(() => {
      fetchDrafts(false);
    }, 30000); // 30 seconds

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      abortControllerRef.current?.abort();
    };
  }, [fetchDrafts]);

  // Optimistic UI update for approve
  const handleApprove = async (draftId: string) => {
    setActionLoading(draftId);
    const previousDrafts = drafts;

    // Optimistic update: remove immediately
    setDrafts((prev) => prev.filter((d) => d.draft_id !== draftId));
    setSelected(null);

    try {
      const res = await fetch(`${API}/api/v1/approvals/${draftId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved_by: "founder" }),
      });

      if (!res.ok) {
        throw new Error(`Approval failed: ${res.status}`);
      }

      // Verify with backend
      await fetchDrafts(false);
    } catch (e) {
      console.error("Approval error:", e);
      // Rollback on error
      setDrafts(previousDrafts);
      setError({
        message: `Failed to approve draft: ${e instanceof Error ? e.message : "Unknown error"}`,
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setActionLoading(null);
    }
  };

  // Optimistic UI update for reject
  const handleReject = async (draftId: string) => {
    setActionLoading(draftId);
    const previousDrafts = drafts;

    // Optimistic update: remove immediately
    setDrafts((prev) => prev.filter((d) => d.draft_id !== draftId));
    setSelected(null);

    try {
      const res = await fetch(`${API}/api/v1/approvals/${draftId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason: "rejected by property manager" }),
      });

      if (!res.ok) {
        throw new Error(`Rejection failed: ${res.status}`);
      }

      // Verify with backend
      await fetchDrafts(false);
    } catch (e) {
      console.error("Rejection error:", e);
      // Rollback on error
      setDrafts(previousDrafts);
      setError({
        message: `Failed to reject draft: ${e instanceof Error ? e.message : "Unknown error"}`,
        timestamp: new Date().toLocaleTimeString(),
      });
    } finally {
      setActionLoading(null);
    }
  };

  const handleManualRefresh = () => {
    fetchDrafts(true);
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
