import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "PropOps — AI Property Operations",
  description: "AI Operational Middleware for Property Managers",
};

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/incidents", label: "Incidents" },
  { href: "/tenants", label: "Tenants" },
  { href: "/vendors", label: "Vendors" },
  { href: "/onboarding", label: "Setup" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-gray-950 text-gray-100 min-h-screen`}>
        <nav className="border-b border-gray-800 bg-gray-900 px-6 py-3 flex items-center gap-6">
          <span className="font-semibold text-white tracking-tight">PropOps</span>
          {NAV_LINKS.map((l) => (
            <Link key={l.href} href={l.href}
              className="text-sm text-gray-400 hover:text-white transition-colors">
              {l.label}
            </Link>
          ))}
        </nav>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
