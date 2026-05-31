"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearToken, getUser, apiFetch } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Queue", icon: "📋", mobileLabel: "Queue" },
  { href: "/incidents", label: "Incidents", icon: "🚨", mobileLabel: "Alerts" },
  { href: "/dashboard", label: "Dashboard", icon: "📊", mobileLabel: "Stats" },
  { href: "/tenants", label: "Tenants", icon: "👥", mobileLabel: "Tenants" },
  { href: "/vendors", label: "Vendors", icon: "🔧", mobileLabel: "Vendors" },
  { href: "/settings", label: "Settings", icon: "⚙️", mobileLabel: "Settings" },
];

const MORE_LINKS = [
  { href: "/onboarding", label: "Setup", icon: "⚙️" },
];

function PendingBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="bg-red-500 text-white text-xs font-bold px-1.5 py-0.5 rounded-full min-w-[1.25rem] text-center">
      {count > 99 ? "99+" : count}
    </span>
  );
}

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
      } catch {
        /* silent — badge optional */
      }
    }
    fetchCount();
    const id = setInterval(fetchCount, 30_000);
    return () => clearInterval(id);
  }, []);

  function logout() {
    clearToken();
    router.push("/login");
  }

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);

  const navLinkClass = (active: boolean) =>
    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
      active ? "bg-blue-600 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800"
    }`;

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex w-52 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex-col h-screen sticky top-0">
        <div className="p-4 border-b border-gray-800">
          <div className="font-bold text-white text-lg">PropOps</div>
          {user && <div className="text-xs text-gray-500 mt-0.5 truncate">{user.email}</div>}
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {LINKS.map((l) => {
            const active = isActive(l.href);
            return (
              <Link key={l.href} href={l.href} className={navLinkClass(active)}>
                <span className="text-base">{l.icon}</span>
                <span>{l.label}</span>
                {l.href === "/" && <span className="ml-auto"><PendingBadge count={pendingCount} /></span>}
              </Link>
            );
          })}
          {MORE_LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={navLinkClass(isActive(l.href))}>
              <span className="text-base">{l.icon}</span>
              <span>{l.label}</span>
            </Link>
          ))}
        </nav>
        <div className="p-3 border-t border-gray-800">
          <button
            type="button"
            onClick={logout}
            className="w-full text-left px-3 py-2 rounded-lg text-sm text-gray-500 hover:text-red-400 hover:bg-gray-800 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Mobile bottom tab bar — icons + short labels */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 flex items-stretch justify-around border-t border-gray-800 bg-gray-900 safe-area-pb"
        aria-label="Main navigation"
      >
        {LINKS.map((l) => {
          const active = isActive(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-[10px] font-medium ${
                active ? "text-blue-400" : "text-gray-500"
              }`}
            >
              <span className="relative text-lg leading-none">
                {l.icon}
                {l.href === "/" && pendingCount > 0 && (
                  <span className="absolute -top-1 -right-2 h-4 min-w-[1rem] px-0.5 rounded-full bg-red-500 text-[9px] text-white font-bold flex items-center justify-center">
                    {pendingCount > 9 ? "9+" : pendingCount}
                  </span>
                )}
              </span>
              <span>{l.mobileLabel}</span>
            </Link>
          );
        })}
      </nav>

      {/* Mobile top bar — brand + user (sidebar header replacement) */}
      <header className="md:hidden sticky top-0 z-30 flex items-center justify-between border-b border-gray-800 bg-gray-950 px-4 py-3">
        <span className="font-bold text-white">PropOps</span>
        {user ? (
          <span className="text-xs text-gray-500 truncate max-w-[50%]">{user.email}</span>
        ) : (
          <button type="button" onClick={logout} className="text-xs text-gray-500">
            Sign out
          </button>
        )}
      </header>
    </>
  );
}
