"use client";
import { useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Loader2, ChevronRight, Calendar, Mail, Tag } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Incident {
  id: string;
  title: string;
  category: string;
  urgency: "EMERGENCY" | "HIGH" | "MEDIUM" | "LOW";
  status: "OPEN" | "PENDING_APPROVAL" | "RESOLVED" | "CLOSED";
  ai_summary: string | null;
  source_address: string | null;
  created_at: string;
  draft_count: number;
}

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
  OPEN: { bg: "bg-blue-950", text: "text-blue-200", dot: "bg-blue-500" },
  PENDING_APPROVAL: { bg: "bg-amber-950", text: "text-amber-200", dot: "bg-amber-500" },
  RESOLVED: { bg: "bg-green-950", text: "text-green-200", dot: "bg-green-500" },
  CLOSED: { bg: "bg-gray-800", text: "text-gray-300", dot: "bg-gray-500" },
};

const urgencyColors: Record<string, { bg: string; text: string; border: string }> = {
  EMERGENCY: { bg: "bg-red-900/20", text: "text-red-300", border: "border-red-700" },
  HIGH: { bg: "bg-orange-900/20", text: "text-orange-300", border: "border-orange-700" },
  MEDIUM: { bg: "bg-yellow-900/20", text: "text-yellow-300", border: "border-yellow-700" },
  LOW: { bg: "bg-green-900/20", text: "text-green-300", border: "border-green-700" },
};

const categoryColors: Record<string, string> = {
  maintenance: "bg-purple-900/20 text-purple-300",
  billing: "bg-indigo-900/20 text-indigo-300",
  noise: "bg-rose-900/20 text-rose-300",
  lease: "bg-cyan-900/20 text-cyan-300",
  general: "bg-gray-800 text-gray-300",
};

function StatusBadge({ status }: { status: string }) {
  const colors = statusColors[status] || statusColors.OPEN;
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg ${colors.bg} ${colors.text} text-xs font-medium`}>
      <span className={`w-2 h-2 rounded-full ${colors.dot}`}></span>
      {status}
    </div>
  );
}

function UrgencyBadge({ urgency }: { urgency: string }) {
  const colors = urgencyColors[urgency] || urgencyColors.MEDIUM;
  return (
    <div className={`px-2.5 py-1 rounded border ${colors.bg} ${colors.text} ${colors.border} text-xs font-semibold`}>
      {urgency}
    </div>
  );
}

function CategoryBadge({ category }: { category: string }) {
  const color = categoryColors[category] || categoryColors.general;
  return (
    <span className={`inline-block px-2.5 py-0.5 rounded text-xs font-medium ${color}`}>
      {category || "uncategorized"}
    </span>
  );
}

function FormatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  } catch {
    return dateStr.split("T")[0];
  }
}

export default function IncidentsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  
  const statusFilter = searchParams.get("status") || "";
  const urgencyFilter = searchParams.get("urgency") || "";

  const fetchIncidents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      if (urgencyFilter) params.append("urgency", urgencyFilter);
      
      const res = await fetch(`${API}/api/v1/incidents?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch incidents");
      const data = await res.json();
      setIncidents(data);
    } catch (e) {
      console.error("Failed to fetch incidents", e);
      setIncidents([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, urgencyFilter]);

  useEffect(() => {
    fetchIncidents();
  }, [fetchIncidents]);

  const handleFilterChange = (key: string, value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    router.push(`/incidents?${params.toString()}`);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-950/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-white">Incidents</h1>
              <p className="text-gray-400 text-sm mt-1">Unified operational view</p>
            </div>
            <Link 
              href="/" 
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-white text-sm font-medium transition-colors"
            >
              ← Back to Queue
            </Link>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          
          {/* Filters Sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-5 sticky top-24">
              <h2 className="text-lg font-semibold text-white mb-4">Filters</h2>
              
              {/* Status Filter */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-300 mb-3">Status</label>
                <div className="space-y-2">
                  {["", "OPEN", "PENDING_APPROVAL", "RESOLVED", "CLOSED"].map(status => (
                    <label key={status} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="status"
                        value={status}
                        checked={statusFilter === status}
                        onChange={(e) => handleFilterChange("status", e.target.value)}
                        className="w-4 h-4 accent-blue-500"
                      />
                      <span className="text-sm text-gray-300">
                        {status || "All Statuses"}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Urgency Filter */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">Urgency</label>
                <div className="space-y-2">
                  {["", "EMERGENCY", "HIGH", "MEDIUM", "LOW"].map(urgency => (
                    <label key={urgency} className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="radio"
                        name="urgency"
                        value={urgency}
                        checked={urgencyFilter === urgency}
                        onChange={(e) => handleFilterChange("urgency", e.target.value)}
                        className="w-4 h-4 accent-blue-500"
                      />
                      <span className="text-sm text-gray-300">
                        {urgency || "All Urgencies"}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              {/* Clear Filters */}
              {(statusFilter || urgencyFilter) && (
                <button
                  onClick={() => router.push("/incidents")}
                  className="mt-6 w-full py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 text-sm font-medium transition-colors"
                >
                  Clear Filters
                </button>
              )}
            </div>
          </div>

          {/* Incidents List */}
          <div className="lg:col-span-3">
            {loading ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
              </div>
            ) : incidents.length === 0 ? (
              <div className="text-center py-20 bg-gray-900 border border-gray-800 rounded-lg">
                <Tag className="w-12 h-12 text-gray-700 mx-auto mb-4" />
                <p className="text-xl text-gray-300 font-medium">No incidents found</p>
                <p className="text-gray-500 text-sm mt-2">
                  {statusFilter || urgencyFilter 
                    ? "Try adjusting your filters"
                    : "Send an email to get started"}
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {incidents.map(incident => (
                  <button
                    key={incident.id}
                    onClick={() => setSelectedId(incident.id)}
                    className="w-full text-left p-4 bg-gray-900 border border-gray-800 hover:border-blue-700 rounded-lg transition-all duration-200 hover:shadow-lg hover:shadow-blue-900/20 group"
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex-1 min-w-0">
                        <h3 className="text-white font-semibold truncate group-hover:text-blue-300 transition-colors">
                          {incident.title}
                        </h3>
                        <div className="flex items-center gap-2 mt-2 text-xs text-gray-400">
                          <Mail className="w-3.5 h-3.5" />
                          <span className="truncate">{incident.source_address || "unknown"}</span>
                        </div>
                      </div>
                      <ChevronRight className="w-5 h-5 text-gray-600 group-hover:text-blue-400 transition-colors shrink-0" />
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mb-3">
                      <CategoryBadge category={incident.category} />
                      <UrgencyBadge urgency={incident.urgency} />
                      <StatusBadge status={incident.status} />
                      {incident.draft_count > 0 && (
                        <span className="px-2.5 py-0.5 rounded text-xs font-medium bg-purple-900/20 text-purple-300 border border-purple-700">
                          {incident.draft_count} draft{incident.draft_count !== 1 ? "s" : ""}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        <span>{FormatDate(incident.created_at)}</span>
                      </div>
                      {incident.ai_summary && (
                        <p className="truncate line-clamp-1">{incident.ai_summary}</p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      {selectedId && (
        <IncidentDetail 
          incidentId={selectedId} 
          onClose={() => setSelectedId(null)}
          onNavigateToDraft={(draftId) => {
            setSelectedId(null);
            router.push(`/?focus=${draftId}`);
          }}
        />
      )}
    </div>
  );
}

interface IncidentDetailProps {
  incidentId: string;
  onClose: () => void;
  onNavigateToDraft: (draftId: string) => void;
}

interface DetailIncident {
  id: string;
  title: string;
  category: string;
  urgency: string;
  status: string;
  summary: string | null;
  source: string | null;
  raw_message: string | null;
  created_at: string;
  drafts: Array<{
    id: string;
    subject: string;
    body: string;
    status: string;
  }>;
  comm_logs: Array<{
    id: string;
    direction: string;
    channel: string;
    sender: string;
    recipient: string;
    subject: string;
    body: string;
    created_at: string;
  }>;
}

function IncidentDetail({ incidentId, onClose, onNavigateToDraft }: IncidentDetailProps) {
  const [incident, setIncident] = useState<DetailIncident | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"message" | "summary" | "drafts" | "logs">("message");

  useEffect(() => {
    const fetchDetail = async () => {
      try {
        const res = await fetch(`${API}/api/v1/incidents/${incidentId}`);
        if (!res.ok) throw new Error("Failed to fetch incident");
        const data = await res.json();
        setIncident(data);
      } catch (e) {
        console.error("Failed to fetch incident detail", e);
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [incidentId]);

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50">
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 max-w-md">
          <p className="text-gray-300">Failed to load incident</p>
          <button
            onClick={onClose}
            className="mt-4 w-full py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 text-sm font-medium"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-800 rounded-lg max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        
        {/* Header */}
        <div className="border-b border-gray-800 px-6 py-4 flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-white truncate">{incident.title}</h2>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <CategoryBadge category={incident.category} />
              <UrgencyBadge urgency={incident.urgency} />
              <StatusBadge status={incident.status} />
            </div>
          </div>
          <button
            onClick={onClose}
            className="ml-4 text-gray-500 hover:text-gray-300 text-2xl font-light"
          >
            ×
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-800 px-6 flex gap-1">
          {["message", "summary", "drafts", "logs"].map(tabName => (
            <button
              key={tabName}
              onClick={() => setTab(tabName as any)}
              className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
                tab === tabName
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-gray-400 hover:text-gray-300"
              }`}
            >
              {tabName.charAt(0).toUpperCase() + tabName.slice(1)}
              {tabName === "drafts" && incident.drafts.length > 0 && (
                <span className="ml-2 text-xs bg-blue-900/30 text-blue-300 px-2 py-0.5 rounded">
                  {incident.drafts.length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {tab === "message" && (
            <div>
              <div className="mb-4">
                <p className="text-xs text-gray-500 font-semibold mb-2">FROM</p>
                <p className="text-gray-200">{incident.source || "unknown"}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 font-semibold mb-2">MESSAGE</p>
                <div className="bg-gray-950 rounded p-4 text-gray-300 text-sm whitespace-pre-wrap leading-relaxed font-mono">
                  {incident.raw_message || "No message content"}
                </div>
              </div>
            </div>
          )}

          {tab === "summary" && (
            <div>
              <p className="text-gray-300 leading-relaxed whitespace-pre-wrap">
                {incident.summary || "No AI summary available"}
              </p>
            </div>
          )}

          {tab === "drafts" && (
            <div className="space-y-4">
              {incident.drafts.length === 0 ? (
                <p className="text-gray-400 text-center py-8">No drafts for this incident</p>
              ) : (
                incident.drafts.map(draft => (
                  <div key={draft.id} className="bg-gray-950 rounded-lg p-4 border border-gray-800">
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div>
                        <p className="text-sm font-semibold text-white">{draft.subject}</p>
                        <span className={`inline-block mt-1 text-xs px-2 py-1 rounded font-medium ${
                          draft.status === "pending" ? "bg-amber-900/30 text-amber-300" :
                          draft.status === "approved" ? "bg-green-900/30 text-green-300" :
                          draft.status === "rejected" ? "bg-red-900/30 text-red-300" :
                          "bg-gray-800 text-gray-300"
                        }`}>
                          {draft.status}
                        </span>
                      </div>
                      {draft.status === "pending" && (
                        <button
                          onClick={() => onNavigateToDraft(draft.id)}
                          className="px-3 py-1 bg-blue-600 hover:bg-blue-500 rounded text-white text-xs font-medium transition-colors shrink-0"
                        >
                          Review
                        </button>
                      )}
                    </div>
                    <div className="bg-gray-900 rounded p-3 text-gray-300 text-sm whitespace-pre-wrap">
                      {draft.body}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {tab === "logs" && (
            <div className="space-y-4">
              {!incident.comm_logs || incident.comm_logs.length === 0 ? (
                <p className="text-gray-400 text-center py-8">No communication logs</p>
              ) : (
                incident.comm_logs.map(log => (
                  <div key={log.id} className="border-l-2 border-gray-700 pl-4 py-2">
                    <div className="flex items-center gap-3 mb-1">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                        log.direction === "inbound" 
                          ? "bg-blue-900/30 text-blue-300"
                          : "bg-green-900/30 text-green-300"
                      }`}>
                        {log.direction.toUpperCase()}
                      </span>
                      <span className="text-xs text-gray-500">{log.channel}</span>
                      <span className="text-xs text-gray-600">{FormatDate(log.created_at)}</span>
                    </div>
                    <p className="text-xs text-gray-400 mb-2">
                      {log.direction === "inbound" ? `From: ${log.sender}` : `To: ${log.recipient}`}
                    </p>
                    {log.subject && (
                      <p className="text-sm font-medium text-gray-300 mb-1">{log.subject}</p>
                    )}
                    <p className="text-sm text-gray-400 whitespace-pre-wrap">{log.body}</p>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-800 px-6 py-4 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-gray-300 text-sm font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
