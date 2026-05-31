"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearToken, getUser, apiFetch } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Queue", icon: "📋" },
  { href: "/incidents", label: "Incidents", icon: "🚨" },
  { href: "/dashboard", label: "Dashboard", icon: "📊" },
  { href: "/tenants", label: "Tenants", icon: "👥" },
  { href: "/vendors", label: "Vendors", icon: "🔧" },
  { href: "/onboarding", label: "Setup", icon: "⚙️" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

export default function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [pendingCount, setPendingCount] = useState(0);
  const user = getUser();

  useEffect(() => {
    async function fetchCount() {
      try {
        const res = await apiFetch("/api/v1/approvals/count");
        if (res.ok) {
          const d = await res.json();
          setPendingCount(d.pending ?? 0);
        }
      } catch { /* silent */ }
    }
    fetchCount();
    const id = setInterval(fetchCount, 30_000);
    return () => clearInterval(id);
  }, []);

  function logout() {
    clearToken();
    router.push("/login");
  }

  return (
    <aside className="w-52 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-screen sticky top-0">
      <div className="p-4 border-b border-gray-800">
        <div className="font-bold text-white text-lg">PropOps</div>
        {user && <div className="text-xs text-gray-500 mt-0.5 truncate">{user.email}</div>}
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {LINKS.map((l) => {
          const active = pathname === l.href;
          return (
            <Link key={l.href} href={l.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${active ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800"}`}>
              <span className="text-base">{l.icon}</span>
              <span>{l.label}</span>
              {l.href === "/" && pendingCount > 0 && (
                <span className="ml-auto bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center">
                  {pendingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-gray-800">
        <button onClick={logout}
          className="w-full text-left px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors">
          Sign out
        </button>
      </div>
    </aside>
  );
}
