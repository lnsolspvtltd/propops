"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { AlertCircle, CheckCircle2, XCircle, RefreshCw, Loader2 } from "lucide-react";

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
      if (!Array.isArray(data)) {
        throw new Error("Invalid response format");
      }

      // Sort by urgency (EMERGENCY first)
      const sorted = data.sort(
        (a, b) =>
          urgencyConfig[a.urgency].order - urgencyConfig[b.urgency].order
      );

      setDrafts(sorted);
      setError(null);
      setLastRefresh(new Date().toLocaleTimeString());

      // Clear selection if selected draft was removed
      if (selected && !sorted.find((d) => d.draft_id === selected.draft_id)) {
        setSelected(null);
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
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-3xl sm:text-4xl font-bold text-white">
                PropOps Approval Queue
              </h1>
              <p className="text-gray-400 mt-1 text-sm">
                Review and approve AI-generated property communications
              </p>
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center gap-3">
              {lastRefresh && (
                <p className="text-gray-500 text-xs">
                  Last updated: {lastRefresh}
                </p>
              )}
              <button
                onClick={handleManualRefresh}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm font-medium text-gray-200 transition-colors"
                aria-label="Refresh drafts"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4" />
                )}
                <span className="hidden sm:inline">Refresh</span>
              </button>
            </div>
          </div>

          {/* Status bar */}
          <div className="mt-4 flex items-center gap-2 text-sm">
            <div
              className={`h-2 w-2 rounded-full ${
                drafts.length === 0 ? "bg-green-500" : "bg-orange-500"
              }`}
              aria-hidden="true"
            />
            <span className="text-gray-400">
              {drafts.length === 0
                ? "All approvals complete"
                : `${drafts.length} pending approval${drafts.length !== 1 ? "s" : ""}`}
            </span>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <ErrorBanner error={error} onDismiss={() => setError(null)} />
        )}

        {/* Content */}
        {loading && drafts.length === 0 ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <DraftSkeleton key={i} />
            ))}
          </div>
        ) : drafts.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 lg:gap-6">
            {/* Draft list */}
            <div className="lg:col-span-1 space-y-3">
              <h2 className="text-sm font-semibold text-gray-300 px-1">
                Pending Drafts
              </h2>
              <div className="space-y-2">
                {drafts.map((draft) => {
                  const config = urgencyConfig[draft.urgency];
                  const isSelected = selected?.draft_id === draft.draft_id;

                  return (
                    <button
                      key={draft.draft_id}
                      onClick={() => setSelected(draft)}
                      className={`w-full text-left p-4 rounded-lg border transition-all ${
                        isSelected
                          ? "border-blue-500 bg-blue-950/30 ring-2 ring-blue-500/50"
                          : "border-gray-800 bg-gray-900 hover:border-gray-700 hover:bg-gray-800/50"
                      }`}
                      aria-pressed={isSelected}
                      aria-label={`Draft: ${draft.incident_title} (${draft.urgency})`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start gap-2">
                            <span className="text-lg flex-shrink-0" aria-hidden="true">
                              {config.icon}
                            </span>
                            <p className="font-medium text-white text-sm truncate">
                              {draft.incident_title}
                            </p>
                          </div>
                          <p className="text-gray-400 text-xs mt-2 truncate">
                            {draft.recipient}
                          </p>
                        </div>
                        <span
                          className={`text-xs px-2.5 py-1 rounded font-medium shrink-0 border ${config.badge}`}
                          aria-label={`Urgency: ${draft.urgency}`}
                        >
                          {draft.urgency}
                        </span>
                      </div>
                      <p className="text-gray-500 text-xs mt-2 line-clamp-1">
                        {draft.subject}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Draft detail panel */}
            {selected && (
              <div className="lg:col-span-2">
                <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden sticky top-4">
                  {/* Detail header */}
                  <div className="bg-gradient-to-r from-gray-900 to-gray-800 border-b border-gray-800 px-5 py-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-2">
                          <span
                            className={`text-xs px-2.5 py-1 rounded font-medium border ${
                              urgencyConfig[selected.urgency].badge
                            }`}
                            aria-label={`Urgency: ${selected.urgency}`}
                          >
                            {selected.urgency}
                          </span>
                          <span className="text-xs text-gray-500">
                            {selected.draft_id.slice(0, 8)}...
                          </span>
                        </div>
                        <h2 className="text-white font-semibold text-lg truncate">
                          {selected.incident_title}
                        </h2>
                        <p className="text-gray-400 text-sm mt-1">
                          To: <span className="text-gray-300">{selected.recipient}</span>
                        </p>
                      </div>
                      <button
                        onClick={() => setSelected(null)}
                        className="text-gray-500 hover:text-gray-300 transition-colors p-1"
                        aria-label="Close detail view"
                      >
                        <XCircle className="w-5 h-5" />
                      </button>
                    </div>
                  </div>

                  {/* Draft content */}
                  <div className="p-5">
                    <div className="bg-gray-950 rounded-lg p-4 mb-6 border border-gray-800">
                      <p className="text-gray-400 text-xs font-mono font-semibold mb-3 uppercase tracking-wider">
                        Subject
                      </p>
                      <p className="text-gray-200 font-medium">{selected.subject}</p>

                      <hr className="border-gray-800 my-4" />

                      <p className="text-gray-400 text-xs font-mono font-semibold mb-3 uppercase tracking-wider">
                        Message Body
                      </p>
                      <div className="text-gray-100 text-sm whitespace-pre-wrap leading-relaxed max-h-96 overflow-y-auto">
                        {selected.body}
                      </div>
                    </div>

                    {/* Action buttons */}
                    <div className="grid grid-cols-2 gap-3">
                      <button
                        onClick={() => handleApprove(selected.draft_id)}
                        disabled={actionLoading === selected.draft_id}
                        className={`py-2.5 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2 ${
                          actionLoading === selected.draft_id
                            ? "bg-gray-800 text-gray-400 cursor-not-allowed"
                            : "bg-green-600 hover:bg-green-700 text-white active:scale-95"
                        }`}
                        aria-busy={actionLoading === selected.draft_id}
                      >
                        {actionLoading === selected.draft_id ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>Approving...</span>
                          </>
                        ) : (
                          <>
                            <CheckCircle2 className="w-4 h-4" />
                            <span>Approve & Send</span>
                          </>
                        )}
                      </button>
                      <button
                        onClick={() => handleReject(selected.draft_id)}
                        disabled={actionLoading === selected.draft_id}
                        className={`py-2.5 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-2 ${
                          actionLoading === selected.draft_id
                            ? "bg-gray-800 text-gray-400 cursor-not-allowed"
                            : "bg-gray-800 hover:bg-red-900 text-gray-200 hover:text-white active:scale-95"
                        }`}
                        aria-busy={actionLoading === selected.draft_id}
                      >
                        {actionLoading === selected.draft_id ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            <span>Rejecting...</span>
                          </>
                        ) : (
                          <>
                            <XCircle className="w-4 h-4" />
                            <span>Reject</span>
                          </>
                        )}
                      </button>
                    </div>

                    {/* Help text */}
                    <p className="text-gray-500 text-xs mt-4 text-center">
                      Approving will send this email to the recipient
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
