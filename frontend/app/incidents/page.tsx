"use client";
import { useCallback, useEffect, useState } from "react";

const ORG_ID = process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? "00000000-0000-0000-0000-000000000001";
const URGENCY_BADGE: Record<string, string> = {
  EMERGENCY: "bg-red-600 text-white", HIGH: "bg-orange-500 text-white",
  MEDIUM: "bg-yellow-500 text-black", LOW: "bg-gray-700 text-gray-300",
};

interface Vendor { id: string; name: string; specialty: string }
interface Incident {
  id: string; title: string; status: string; urgency: string | null;
  category: string | null; vendor_id: string | null; created_at: string;
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [assigning, setAssigning] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [ir, vr] = await Promise.all([
      fetch("/api/v1/incidents/"),
      fetch(`/api/v1/vendors/?org_id=${ORG_ID}`),
    ]);
    if (ir.ok) setIncidents(await ir.json());
    if (vr.ok) setVendors(await vr.json());
  }, []);
  useEffect(() => { load(); }, [load]);

  async function assign(incidentId: string, vendorId: string) {
    await fetch(`/api/v1/incidents/${incidentId}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ vendor_id: vendorId }),
    });
    setAssigning(null);
    load();
  }

  async function resolve(incidentId: string) {
    if (!confirm("Mark this incident as resolved?")) return;
    await fetch(`/api/v1/incidents/${incidentId}/resolve`, { method: "POST" });
    load();
  }

  const vendorForCategory = (cat: string | null) =>
    vendors.filter((v) => !cat || v.specialty === cat.toLowerCase());

  return (
    <div className="space-y-5 max-w-5xl">
      <h1 className="text-xl font-semibold text-white">Incidents</h1>
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        {incidents.length === 0
          ? <p className="text-gray-500 text-sm">No incidents.</p>
          : <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                {["Urgency", "Subject", "Category", "Status", "Assigned To", "Actions"].map((h) =>
                  <th key={h} className="pb-2 pr-4 text-xs">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {incidents.map((i) => (
                <tr key={i.id} className="border-b border-gray-800/50 hover:bg-gray-800/30 align-top">
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${URGENCY_BADGE[i.urgency ?? ""] ?? "bg-gray-700 text-gray-300"}`}>
                      {i.urgency ?? "—"}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-white max-w-xs truncate">{i.title}</td>
                  <td className="py-2 pr-4 text-gray-400 capitalize">{i.category ?? "—"}</td>
                  <td className="py-2 pr-4">
                    <span className={`px-2 py-0.5 rounded-full text-xs ${i.status === "CLOSED" ? "bg-green-900 text-green-300" : "bg-gray-800 text-gray-300"}`}>
                      {i.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-gray-400">
                    {i.vendor_id
                      ? <span className="text-green-400 text-xs">
                          {vendors.find((v) => v.id === i.vendor_id)?.name ?? "Assigned"}
                        </span>
                      : <span className="text-gray-600 text-xs">Unassigned</span>
                    }
                  </td>
                  <td className="py-2 space-x-2">
                    {i.status !== "CLOSED" && (
                      <>
                        {assigning === i.id
                          ? <select autoFocus defaultValue=""
                              onChange={(e) => e.target.value && assign(i.id, e.target.value)}
                              onBlur={() => setAssigning(null)}
                              className="text-xs rounded bg-gray-800 border border-gray-700 px-2 py-1 text-white">
                              <option value="" disabled>Pick vendor…</option>
                              {(vendorForCategory(i.category).length > 0
                                ? vendorForCategory(i.category)
                                : vendors
                              ).map((v) => (
                                <option key={v.id} value={v.id}>{v.name}</option>
                              ))}
                            </select>
                          : !i.vendor_id
                            ? <button onClick={() => setAssigning(i.id)}
                                className="text-xs text-blue-400 hover:text-blue-300">Assign</button>
                            : <button onClick={() => setAssigning(i.id)}
                                className="text-xs text-gray-400 hover:text-gray-300">Reassign</button>
                        }
                        <button onClick={() => resolve(i.id)}
                          className="text-xs text-green-400 hover:text-green-300">Resolve</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      </div>
    </div>
  );
}
