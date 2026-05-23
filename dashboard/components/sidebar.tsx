"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { Activity, BarChart3, Brain, History, Inbox, ScrollText, Settings as SettingsIcon, Sparkles } from "lucide-react";
import { fetcher, StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/queue", label: "Draft Queue", icon: Inbox },
  { href: "/logs", label: "Live Logs", icon: ScrollText },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

const dot = {
  running: "bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.7)]",
  paused: "bg-amber-400 shadow-[0_0_12px_rgba(251,191,36,0.7)]",
  stopped: "bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.7)]",
} as const;

export function Sidebar() {
  const pathname = usePathname();
  const { data } = useSWR<StatusResponse>("/api/status", fetcher, { refreshInterval: 5000 });
  const status = data?.status ?? "stopped";

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col gap-2 p-5 border-r border-border bg-black/60 h-screen sticky top-0">
      <div className="flex items-center gap-2 mb-6">
        <div className="relative w-9 h-9 rounded-xl bg-gradient-to-br from-lavender to-lavender-deep flex items-center justify-center lavender-glow">
          <Sparkles size={18} className="text-black" />
        </div>
        <div>
          <div className="font-semibold leading-tight">X Bot</div>
          <div className="text-xs text-muted">Control Center</div>
        </div>
      </div>

      <div className="glass px-3 py-2 mb-3 flex items-center gap-2 text-xs">
        <span className={cn("w-2 h-2 rounded-full", dot[status])} />
        <span className="uppercase tracking-wider">{status}</span>
      </div>

      <nav className="flex flex-col gap-1">
        {nav.map((n) => {
          const active = pathname === n.href || (n.href !== "/" && pathname.startsWith(n.href));
          const Icon = n.icon;
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition",
                active
                  ? "bg-lavender/15 text-lavender border border-lavender/30"
                  : "text-muted hover:text-white hover:bg-white/5"
              )}
            >
              <Icon size={16} />
              {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto text-xs text-muted/70 mono">
        api: {process.env.NEXT_PUBLIC_API_URL || "localhost:8000"}
      </div>
    </aside>
  );
}
