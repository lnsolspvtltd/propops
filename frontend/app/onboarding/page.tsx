"use client";
import { useState } from "react";

type Step = "email" | "org" | "done";

interface ImapForm {
  imap_host: string; imap_port: string; imap_username: string; imap_password: string;
  smtp_host: string; smtp_port: string; smtp_username: string; smtp_password: string;
}
const EMPTY_IMAP: ImapForm = {
  imap_host: "", imap_port: "993", imap_username: "", imap_password: "",
  smtp_host: "", smtp_port: "587", smtp_username: "", smtp_password: "",
};

function Input({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-400">{label}</label>
      <input {...props}
        className="w-full rounded bg-gray-800 border border-gray-700 px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500" />
    </div>
  );
}

export default function OnboardingPage() {
  const [step, setStep] = useState<Step>("email");
  const [imap, setImap] = useState<ImapForm>(EMPTY_IMAP);
  const [orgName, setOrgName] = useState("");
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [testError, setTestError] = useState("");
  const [saving, setSaving] = useState(false);
  const [orgId, setOrgId] = useState("");

  function field(k: keyof ImapForm) {
    return { value: imap[k], onChange: (e: React.ChangeEvent<HTMLInputElement>) => setImap((p) => ({ ...p, [k]: e.target.value })) };
  }

  async function testImap() {
    setTestStatus("testing");
    setTestError("");
    try {
      const r = await fetch("/api/v1/onboarding/test-imap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...imap, imap_port: Number(imap.imap_port), smtp_port: Number(imap.smtp_port) }),
      });
      if (r.ok) { setTestStatus("ok"); }
      else { const d = await r.json(); setTestStatus("error"); setTestError(d?.error ?? "Connection failed"); }
    } catch { setTestStatus("error"); setTestError("Network error"); }
  }

  async function setup() {
    setSaving(true);
    try {
      const r = await fetch("/api/v1/onboarding/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          org_name: orgName, ...imap,
          imap_port: Number(imap.imap_port), smtp_port: Number(imap.smtp_port),
        }),
      });
      if (r.ok) { const d = await r.json(); setOrgId(d.org_id); setStep("done"); }
      else { const d = await r.json(); alert(d?.error ?? "Setup failed"); }
    } catch { alert("Network error"); } finally { setSaving(false); }
  }

  if (step === "done") return (
    <div className="max-w-lg space-y-6">
      <div className="rounded-xl border border-green-800 bg-green-950/30 p-6 space-y-3">
        <h1 className="text-xl font-semibold text-green-400">✓ Setup complete</h1>
        <p className="text-gray-300 text-sm">Your inbox is now being monitored. Org ID: <code className="text-xs text-gray-400">{orgId}</code></p>
      </div>
      <div className="flex gap-4 text-sm">
        <a href="/tenants" className="text-blue-400 hover:text-blue-300">→ Set up tenants</a>
        <a href="/vendors" className="text-blue-400 hover:text-blue-300">→ Set up vendors</a>
        <a href="/" className="text-blue-400 hover:text-blue-300">→ Dashboard</a>
      </div>
    </div>
  );

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-white">Organisation Setup</h1>
        <p className="text-gray-400 text-sm mt-1">Connect your property management inbox to get started.</p>
      </div>

      {/* Step 1 — Email */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300">Step 1 — Email Connection</h2>
        <div className="grid grid-cols-2 gap-3">
          <Input label="IMAP Host" placeholder="imap.gmail.com" {...field("imap_host")} />
          <Input label="IMAP Port" type="number" {...field("imap_port")} />
          <Input label="Email address" type="email" {...field("imap_username")} />
          <Input label="Password" type="password" {...field("imap_password")} />
          <Input label="SMTP Host" placeholder="smtp.gmail.com" {...field("smtp_host")} />
          <Input label="SMTP Port" type="number" {...field("smtp_port")} />
          <Input label="SMTP Username" type="email" {...field("smtp_username")} />
          <Input label="SMTP Password" type="password" {...field("smtp_password")} />
        </div>
        <div className="flex items-center gap-3">
          <button onClick={testImap} disabled={testStatus === "testing"}
            className="px-3 py-1.5 text-sm rounded border border-gray-700 text-gray-300 hover:border-gray-500 disabled:opacity-50">
            {testStatus === "testing" ? "Testing…" : "Test Connection"}
          </button>
          {testStatus === "ok" && <span className="text-green-400 text-sm">✓ Connected</span>}
          {testStatus === "error" && <span className="text-red-400 text-sm">✗ {testError}</span>}
        </div>
      </div>

      {/* Step 2 — Org name */}
      {(testStatus === "ok" || step === "org") && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-300">Step 2 — Organisation Name</h2>
          <Input label="Company / organisation name" placeholder="Acme Property Management"
            value={orgName} onChange={(e) => setOrgName(e.target.value)} />
          <button onClick={setup} disabled={saving || !orgName.trim()}
            className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-50">
            {saving ? "Setting up…" : "Complete Setup"}
          </button>
        </div>
      )}
    </div>
  );
}
