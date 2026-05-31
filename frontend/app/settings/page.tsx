"use client";
import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

interface OrgStatus { org_id: string; name: string; polling_active: boolean; imap_connected: boolean }

export default function SettingsPage() {
  const [status, setStatus] = useState<OrgStatus | null>(null);
  const [form, setForm] = useState({
    imap_host: "", imap_port: "993", imap_username: "", imap_password: "",
    smtp_host: "", smtp_port: "587", smtp_username: "", smtp_password: "",
    polling_active: true,
  });
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const orgId = typeof window !== "undefined" ? (process.env.NEXT_PUBLIC_DEFAULT_ORG_ID ?? "") : "";

  useEffect(() => {
    if (!orgId) return;
    apiFetch(`/api/v1/onboarding/status?org_id=${orgId}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d) setStatus(d); })
      .catch(() => {});
  }, [orgId]);

  async function testImap() {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await apiFetch("/api/v1/onboarding/test-imap", {
        method: "POST",
        body: JSON.stringify({ imap_host: form.imap_host, imap_port: Number(form.imap_port), imap_username: form.imap_username, imap_password: form.imap_password }),
      });
      const d = await res.json();
      setTestResult({ ok: res.ok, msg: res.ok ? "Connected successfully" : d?.detail?.error ?? "Failed" });
    } catch { setTestResult({ ok: false, msg: "Network error" }); }
    finally { setTesting(false); }
  }

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, string | number | boolean> = {};
      if (form.imap_host) body.imap_host = form.imap_host;
      if (form.imap_port) body.imap_port = Number(form.imap_port);
      if (form.imap_username) body.imap_username = form.imap_username;
      if (form.imap_password) body.imap_password = form.imap_password;
      if (form.smtp_host) body.smtp_host = form.smtp_host;
      if (form.smtp_port) body.smtp_port = Number(form.smtp_port);
      body.polling_active = form.polling_active;
      await apiFetch("/api/v1/onboarding/settings", { method: "PUT", body: JSON.stringify(body) });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally { setSaving(false); }
  }

  function field(key: keyof typeof form) {
    return { value: form[key] as string, onChange: (e: React.ChangeEvent<HTMLInputElement>) => setForm((p) => ({ ...p, [key]: e.target.value })) };
  }

  const inputCls = "w-full rounded-lg bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500";

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold text-white">Settings</h1>

      {status && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 flex items-center gap-3">
          <span className={`w-2.5 h-2.5 rounded-full ${status.imap_connected ? "bg-green-500" : "bg-red-500"}`} />
          <div>
            <p className="text-sm text-white font-medium">{status.name}</p>
            <p className="text-xs text-gray-400">{status.imap_connected ? "IMAP connected" : "IMAP disconnected"} · polling {status.polling_active ? "active" : "paused"}</p>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300">Email Connection</h2>
        <div className="grid grid-cols-2 gap-3">
          {[
            { label: "IMAP Host", key: "imap_host", placeholder: "imap.gmail.com" },
            { label: "IMAP Port", key: "imap_port", placeholder: "993" },
            { label: "Email address", key: "imap_username", placeholder: "pm@example.com" },
            { label: "IMAP Password", key: "imap_password", placeholder: "Leave blank to keep current", type: "password" },
            { label: "SMTP Host", key: "smtp_host", placeholder: "smtp.gmail.com" },
            { label: "SMTP Port", key: "smtp_port", placeholder: "587" },
            { label: "SMTP Username", key: "smtp_username", placeholder: "pm@example.com" },
            { label: "SMTP Password", key: "smtp_password", placeholder: "Leave blank to keep current", type: "password" },
          ].map(({ label, key, placeholder, type }) => (
            <div key={key}>
              <label className="block text-xs text-gray-400 mb-1">{label}</label>
              <input {...field(key as keyof typeof form)} placeholder={placeholder} type={type ?? "text"} className={inputCls} />
            </div>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button onClick={testImap} disabled={testing}
            className="px-4 py-2 text-sm rounded-lg border border-gray-700 text-gray-300 hover:border-gray-500 disabled:opacity-50">
            {testing ? "Testing…" : "Test Connection"}
          </button>
          {testResult && (
            <span className={`text-sm ${testResult.ok ? "text-green-400" : "text-red-400"}`}>
              {testResult.ok ? "✓" : "✗"} {testResult.msg}
            </span>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Polling</h2>
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={form.polling_active}
            onChange={(e) => setForm((p) => ({ ...p, polling_active: e.target.checked }))}
            className="w-4 h-4 accent-blue-500" />
          <span className="text-sm text-gray-300">Enable automatic inbox polling</span>
        </label>
      </div>

      <button onClick={save} disabled={saving}
        className="px-6 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-semibold text-sm transition-colors">
        {saving ? "Saving…" : saved ? "✓ Saved" : "Save Changes"}
      </button>
    </div>
  );
}
