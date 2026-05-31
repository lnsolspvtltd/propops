/**
 * Authenticated fetch wrapper.
 * Reads token from localStorage, adds Authorization header.
 * Redirects to /login on 401.
 */
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
    if (typeof window !== "undefined") window.location.href = "/login";
  }
  return res;
}
