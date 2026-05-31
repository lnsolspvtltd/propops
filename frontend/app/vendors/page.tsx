"use client";
import { useCallback, useEffect, useState } from "react";

const ORG_ID = process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? "00000000-0000-0000-0000-000000000001";
const SPECIALTIES = ["plumbing", "electrical", "hvac", "general", "cleaning"];

interface Vendor { id: string; name: string; email: string; phone: string | null; specialty: string }
interface Form { name: string; email: string; phone: string; specialty: string }
const EMPTY: Form = { name: "", email: "", phone: "", specialty: "general" };

export default function VendorsPage() {
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [form, setForm] = useState<Form>(EMPTY);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    const r = await fetch(`/api/v1/vendors/?org_id=${ORG_ID}`);
    if (r.ok) setVendors(await r.json());
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    await fetch("/api/v1/vendors/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ org_id: ORG_ID, ...form }),
    });
    setForm(EMPTY);
    setShowForm(false);
    setLoading(false);
    load();
  }

  async function del(id: string) {
    if (!confirm("Remove this vendor?")) return;
    await fetch(`/api/v1/vendors/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="space-y-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Vendors</h1>
        <button onClick={() => setShowForm(!showForm)}
          className="px-3 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white">
          + Add Vendor
        </button>
      </div>

      {showForm && (
        <form onSubmit={create} className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-3">
          <h2 className="text-sm font-semibold text-gray-300">New Vendor</h2>
          <div className="grid grid-cols-2 gap-3">
            {(["name", "email", "phone"] as const).map((f) => (
              <input key={f} required={f !== "phone"} placeholder={f.charAt(0).toUpperCase() + f.slice(1)}
                value={form[f]}
                onChange={(e) => setForm((p) => ({ ...p, [f]: e.target.value }))}
                className="rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
            ))}
            <select value={form.specialty}
              onChange={(e) => setForm((p) => ({ ...p, specialty: e.target.value }))}
              className="rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500">
              {SPECIALTIES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={loading}
              className="px-4 py-1.5 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
              {loading ? "Saving…" : "Save"}
            </button>
            <button type="button" onClick={() => setShowForm(false)}
              className="px-4 py-1.5 text-sm rounded border border-gray-700 text-gray-400">Cancel</button>
          </div>
        </form>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        {vendors.length === 0
          ? <p className="text-gray-500 text-sm">No vendors yet.</p>
          : <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400 text-left">
                {["Name", "Email", "Phone", "Specialty", ""].map((h) =>
                  <th key={h} className="pb-2 pr-4">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {vendors.map((v) => (
                <tr key={v.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="py-2 pr-4 text-white">{v.name}</td>
                  <td className="py-2 pr-4 text-gray-300">{v.email}</td>
                  <td className="py-2 pr-4 text-gray-400">{v.phone ?? "—"}</td>
                  <td className="py-2 pr-4">
                    <span className="px-2 py-0.5 rounded-full text-xs bg-gray-800 text-gray-300 capitalize">{v.specialty}</span>
                  </td>
                  <td className="py-2">
                    <button onClick={() => del(v.id)} className="text-xs text-red-400 hover:text-red-300">Remove</button>
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
