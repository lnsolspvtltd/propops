"use client";
import { usePathname } from "next/navigation";
import NavBar from "./NavBar";

export default function NavWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const showNav = pathname !== "/login";
  return (
    <div className={`flex min-h-screen flex-1 flex-col md:flex-row ${showNav ? "" : "w-full"}`}>
      {showNav && <NavBar />}
      <main className={`flex-1 overflow-y-auto ${showNav ? "pb-20 md:pb-0" : ""}`}>
        {children}
      </main>
    </div>
  );
}
