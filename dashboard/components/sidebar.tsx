"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import { Activity, BarChart3, Brain, History, Inbox, MessageSquare, ScrollText, Settings as SettingsIcon, Sparkles } from "lucide-react";
import { fetcher, NudgeItem, StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/chat", label: "Co-Pilot", icon: MessageSquare },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/queue", label: "Draft Queue", icon: Inbox },
  { href: "/logs", label: "Live Logs", icon: ScrollText },
  { href: "/history", label: "History", icon: History },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

const statusStyle = {
  running: { dot: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.7)]", text: "text-emerald-300", label: "Running" },
  paused: { dot: "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.7)]", text: "text-amber-300", label: "Paused" },
  stopped: { dot: "bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.7)]", text: "text-rose-300", label: "Stopped" },
} as const;

export function Sidebar() {
  const pathname = usePathname();
  const { data } = useSWR<StatusResponse>("/api/status", fetcher, { refreshInterval: 5000 });
  const { data: nudges } = useSWR<NudgeItem[]>("/api/nudges", fetcher, { refreshInterval: 15000 });
  const status = data?.status ?? "stopped";
  const nudgeCount = nudges?.length ?? 0;
  const st = statusStyle[status];

  return (
    <aside className="hidden md:flex w-64 shrink-0 flex-col gap-2 px-4 py-5 border-r border-border h-screen sticky top-0">
      <div className="flex items-center gap-2.5 mb-6 px-1">
        <div className="relative w-9 h-9 rounded-2xl bg-gradient-to-br from-lavender to-lavender-deep flex items-center justify-center lavender-glow">
          <Sparkles size={18} className="text-black" />
        </div>
        <div>
          <div className="font-semibold leading-tight tracking-tight">Twitter Growth</div>
          <div className="text-xs text-muted">System</div>
        </div>
      </div>

      {/* Status pill */}
      <div className="glass pill px-3.5 py-2 mb-3 flex items-center gap-2 text-sm w-fit">
        <span className={cn("w-2 h-2 rounded-full", st.dot)} />
        <span className={cn("font-medium", st.text)}>{st.label}</span>
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
                "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-150",
                active
                  ? "bg-lavender-soft text-lavender border border-lavender/25 shadow-[0_0_0_1px_rgba(167,139,250,0.06)]"
                  : "text-muted hover:text-white hover:bg-white/[0.04] border border-transparent"
              )}
            >
              <Icon size={17} className={active ? "text-lavender" : ""} />
              <span className="flex-1">{n.label}</span>
              {n.href === "/chat" && nudgeCount > 0 && (
                <span className="ml-auto min-w-5 h-5 px-1.5 rounded-full bg-lavender text-black text-[11px] font-bold flex items-center justify-center">
                  {nudgeCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto flex items-center gap-2 px-2 text-xs text-muted/70">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/80" />
        Connected
      </div>
    </aside>
  );
}
