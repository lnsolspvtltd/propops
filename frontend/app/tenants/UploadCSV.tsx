"use client";
import { useRef, useState } from "react";
interface Result { created: number; skipped: number; errors: string[] }
interface Props { orgId: string; onDone: () => void }

export default function UploadCSV({ orgId, onDone }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);

  async function handle(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setResult(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await fetch(`/api/v1/tenants/bulk?org_id=${orgId}`, { method: "POST", body: fd });
      const data: Result = await r.json();
      setResult(data);
      onDone();
    } catch {
      setResult({ created: 0, skipped: 0, errors: ["Upload failed — check console"] });
    } finally {
      setLoading(false);
      if (ref.current) ref.current.value = "";
    }
  }

  return (
    <div className="flex items-center gap-3">
      <input ref={ref} type="file" accept=".csv" onChange={handle} className="hidden" id="csv-input" />
      <label htmlFor="csv-input"
        className="cursor-pointer px-3 py-1.5 text-sm rounded border border-gray-700 text-gray-300 hover:border-gray-500 transition-colors">
        {loading ? "Uploading…" : "Upload CSV"}
      </label>
      {result && (
        <span className="text-xs text-gray-400">
          ✓ {result.created} created, {result.skipped} skipped
          {result.errors.length > 0 && <span className="text-red-400 ml-2">{result.errors.length} errors</span>}
        </span>
      )}
    </div>
  );
}
