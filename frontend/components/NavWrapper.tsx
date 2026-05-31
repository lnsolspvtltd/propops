"use client";
import { usePathname } from "next/navigation";
import NavBar from "./NavBar";

export default function NavWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const showNav = pathname !== "/login";
  return (
    <>
      {showNav && <NavBar />}
      <main className={`flex-1 overflow-y-auto ${showNav ? "" : "w-full"}`}>
        {children}
      </main>
    </>
  );
}
