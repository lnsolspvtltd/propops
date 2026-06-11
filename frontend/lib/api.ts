/**
 * Authenticated fetch wrapper and auth API helpers.
 * Reads token from localStorage, adds Authorization header.
 * Redirects to /login on 401.
 */
function resolveApiBase(): string {
  const url = process.env.NEXT_PUBLIC_API_URL;
  if (url) return url;
  if (process.env.NODE_ENV === "development") return "http://localhost:8000";
  throw new Error("NEXT_PUBLIC_API_URL must be set in non-development builds");
}

const API_BASE = resolveApiBase();

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("propops_token");
}

export function setToken(token: string): void {
  localStorage.setItem("propops_token", token);
}

export function clearToken(): void {
  localStorage.removeItem("propops_token");
  localStorage.removeItem("propops_user");
}

export function getUser(): { email: string; name?: string; org_id?: string; role?: string } | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("propops_user");
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: HeadersInit = {
    "Accept": "application/json",
    ...(options.headers ?? {}),
  };
  if (token) {
    (headers as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }
  if (options.body && typeof options.body === "string") {
    (headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    const err = new Error("Unauthorized — please log in again");
    if (typeof window !== "undefined") window.location.href = "/login";
    throw err;
  }
  return res;
}

// ---------------------------------------------------------------------------
// Auth API helpers
// ---------------------------------------------------------------------------

async function authPost(path: string, body: object): Promise<{ ok: boolean; status: number; data: unknown }> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function extractError(data: unknown): string {
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    if (d.detail && typeof d.detail === "object") {
      const detail = d.detail as Record<string, unknown>;
      return String(detail.message ?? detail.error ?? "Unknown error");
    }
    return String(d.message ?? d.error ?? d.detail ?? "Unknown error");
  }
  return "Unknown error";
}

export async function login(
  email: string,
  password: string,
  orgId: string,
): Promise<{ access_token: string; user: Record<string, string> }> {
  const { ok, data } = await authPost("/api/v1/auth/login", { email, password, org_id: orgId });
  if (!ok) throw new Error(extractError(data));
  return data as { access_token: string; user: Record<string, string> };
}

export async function register(
  email: string,
  password: string,
  orgId: string,
): Promise<{ id: string; email: string; org_id: string; role: string }> {
  const { ok, data } = await authPost("/api/v1/auth/register", { email, password, org_id: orgId });
  if (!ok) throw new Error(extractError(data));
  return data as { id: string; email: string; org_id: string; role: string };
}

export async function verifyEmail(token: string): Promise<void> {
  const { ok, data } = await authPost("/api/v1/auth/verify-email", { token });
  if (!ok) throw new Error(extractError(data));
}

export async function resendVerification(email: string, orgId: string): Promise<void> {
  await authPost("/api/v1/auth/resend-verification", { email, org_id: orgId });
  // Always 202 — no error thrown
}

export async function forgotPassword(email: string, orgId: string): Promise<void> {
  await authPost("/api/v1/auth/forgot-password", { email, org_id: orgId });
  // Always 202 — no error thrown
}

export async function resetPassword(token: string, newPassword: string): Promise<void> {
  const { ok, data } = await authPost("/api/v1/auth/reset-password", { token, new_password: newPassword });
  if (!ok) throw new Error(extractError(data));
}
