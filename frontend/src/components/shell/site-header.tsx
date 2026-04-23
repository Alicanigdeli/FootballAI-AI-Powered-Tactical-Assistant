"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Database, LayoutGrid, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Özet", icon: LayoutGrid },
  { href: "/data", label: "Veri & senkron", icon: Database },
  { href: "/match-analysis", label: "Maç analizi", icon: Activity },
  { href: "/simulation", label: "Taktik sim", icon: Sparkles },
];

export function SiteHeader() {
  const path = usePathname() || "/";
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--header)]/95 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <span className="rounded-md bg-gradient-to-br from-cyan-500 to-blue-700 px-2 py-0.5 text-xs text-white">
            FTAI
          </span>
          <span className="text-sm text-[var(--foreground)]">Tactical Assistant</span>
        </Link>
        <nav className="flex flex-wrap items-center gap-1">
          {links.map(({ href, label, icon: Icon }) => {
            const active = path === href || (href !== "/" && path.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                  active ?
                    "bg-[var(--primary)]/15 text-cyan-300"
                  : "text-[var(--muted-foreground)] hover:bg-[var(--muted)]/40 hover:text-[var(--foreground)]"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
