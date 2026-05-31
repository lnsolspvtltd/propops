"use client";
import { useCallback, useEffect, useState } from "react";
import TenantTable from "./TenantTable";
import UploadCSV from "./UploadCSV";

// TODO: replace with real org_id from auth context in Phase 3
const ORG_ID = process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? "00000000-0000-0000-0000-000000000001";

interface Tenant {
  id: string; name: string; email: string;
  phone: string | null; unit_id: string | null;
}
interface Form { name: string; email: string; phone: string }
const EMPTY: Form = { name: "", email: "", phone: "" };

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/v1/tenants/?org_id=${ORG_ID}`);
    if (r.ok) setTenants(await r.json());
  }, []);

  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    await fetch("/api/v1/tenants/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ org_id: ORG_ID, ...form }),
    });
    setForm(EMPTY);
    setShowForm(false);
    setLoading(false);
    load();
  }

  async function deleteTenant(id: string) {
    if (!confirm("Delete this tenant?")) return;
    await fetch(`/api/v1/tenants/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Tenants</h1>
        <div className="flex items-center gap-3">
          <UploadCSV orgId={ORG_ID} onDone={load} />
          <button onClick={() => setShowForm(!showForm)}
            className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white transition-colors">
            + Add Tenant
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={create} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-300">New Tenant</h2>
          <div className="grid grid-cols-3 gap-3">
            {(["name", "email", "phone"] as const).map((f) => (
              <input key={f} required={f !== "phone"} placeholder={f.charAt(0).toUpperCase() + f.slice(1)}
                value={form[f]}
                onChange={(e) => setForm((p) => ({ ...p, [f]: e.target.value }))}
                className="rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
            ))}
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={loading}
              className="px-4 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
              {loading ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="px-4 py-1.5 text-sm rounded border border-gray-700 text-gray-400 hover:text-white">
              Cancel
            </button>
          </div>
        </form>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <TenantTable tenants={tenants} onDelete={deleteTenant} />
      </div>
    </div>
  );
}
