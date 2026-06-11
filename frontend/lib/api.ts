/**
 * Authenticated fetch wrapper.
 * Reads token from localStorage, adds Authorization header.
 * Redirects to /login on 401.
 *
 * SECURITY NOTE: Tokens are stored in localStorage for the demo/beta UI.
 * This is vulnerable to XSS — any script on the page can read the token.
 * Production hardening should move to httpOnly Secure SameSite cookies set by
 * the backend login endpoint. Until then, keep CSP strict and avoid inline scripts.
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

export function getUser(): { email: string; name: string } | null {
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
