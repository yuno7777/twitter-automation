"use client";

import useSWR from "swr";
import { useEffect, useState } from "react";
import { Play, Pause, Square, RotateCcw, MessageCircle, MessagesSquare, UserPlus, Cpu, Heart, AlertTriangle, Cookie, ShieldAlert } from "lucide-react";
import {
  controlBot,
  CookieStatusResponse,
  fetcher,
  FollowHistoryItem,
  HealthResponse,
  ReplyHistoryItem,
  StatsResponse,
  StatusResponse,
  TweetHistoryItem,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { toast } from "sonner";

const statusStyle = {
  running: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  paused: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  stopped: "bg-rose-500/15 text-rose-300 border-rose-500/40",
} as const;

function Countdown({ to }: { to: string | null | undefined }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!to) return <span className="mono text-muted">—</span>;
  const diff = Math.max(0, Math.floor((new Date(to).getTime() - now) / 1000));
  const h = Math.floor(diff / 3600);
  const m = Math.floor((diff % 3600) / 60);
  const s = diff % 60;
  return (
    <span className="mono text-2xl text-lavender">
      {String(h).padStart(2, "0")}:{String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
    </span>
  );
}

function StatCard({ icon: Icon, label, value }: { icon: any; label: string; value: number | string }) {
  return (
    <div className="glass p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{label}</div>
        <Icon size={16} className="text-lavender" />
      </div>
      <div className="mt-2 text-3xl font-semibold mono">{value}</div>
    </div>
  );
}

async function handleControl(action: "start" | "pause" | "resume" | "stop" | "reset_cycle") {
  try {
    await controlBot(action);
    const label = action === "reset_cycle" ? "Cycle reset — bot will start a new cycle now" : `Bot ${action}`;
    toast.success(label);
  } catch (e: any) {
    toast.error(e.message || "Control failed");
  }
}

export default function OverviewPage() {
  const { data: status } = useSWR<StatusResponse>("/api/status", fetcher, { refreshInterval: 3000 });
  const { data: stats } = useSWR<StatsResponse>("/api/stats", fetcher, { refreshInterval: 5000 });
  const { data: tweets } = useSWR<TweetHistoryItem[]>("/api/history/tweets", fetcher, { refreshInterval: 10000 });
  const { data: replies } = useSWR<ReplyHistoryItem[]>("/api/history/replies", fetcher, { refreshInterval: 10000 });
  const { data: follows } = useSWR<FollowHistoryItem[]>("/api/history/follows", fetcher, { refreshInterval: 10000 });
  const { data: health } = useSWR<HealthResponse>("/api/health", fetcher, { refreshInterval: 30000 });
  const { data: cookie } = useSWR<CookieStatusResponse>("/api/cookie_status", fetcher, { refreshInterval: 60000 });

  const s = status?.status ?? "stopped";

  const activity = [
    ...(tweets || []).slice(0, 5).map((t) => ({
      type: "tweet" as const,
      ts: t.posted_at,
      text: t.text,
    })),
    ...(replies || []).slice(0, 5).map((r) => ({
      type: "reply" as const,
      ts: r.posted_at,
      text: r.reply_text,
    })),
    ...(follows || []).slice(0, 5).map((f) => ({
      type: "follow" as const,
      ts: f.followed_at,
      text: `@${f.username}`,
    })),
  ]
    .sort((a, b) => +new Date(b.ts) - +new Date(a.ts))
    .slice(0, 8);

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold tracking-tight">Overview</h1>
        <p className="text-muted text-sm">Real-time view of your Twitter Growth System.</p>
      </header>

      {/* Health banner — critical if X is showing suspension warnings */}
      {health && health.status === "critical" && (
        <div className="glass p-4 border-rose-500/50 bg-rose-500/10 flex items-start gap-3">
          <ShieldAlert className="text-rose-300 shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <div className="font-semibold text-rose-300">Account health critical — bot auto-paused</div>
            <div className="text-xs text-muted mt-1">
              X showed: {health.warnings.map((w) => w.phrase).join(" · ")}
            </div>
          </div>
        </div>
      )}
      {health && health.status === "warning" && (
        <div className="glass p-4 border-amber-500/50 bg-amber-500/10 flex items-start gap-3">
          <AlertTriangle className="text-amber-300 shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <div className="font-semibold text-amber-300">Account health warning</div>
            <div className="text-xs text-muted mt-1">
              {health.warnings.map((w) => w.phrase).join(" · ")}
              {health.delta < 0 && <span> · follower change {health.delta}</span>}
            </div>
          </div>
        </div>
      )}
      {health && health.consecutive_error_cycles >= 2 && (
        <div className="glass p-4 border-amber-500/40 bg-amber-500/5 flex items-start gap-3">
          <AlertTriangle className="text-amber-300 shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <div className="font-semibold text-amber-300">
              Adaptive backoff active — cooldowns x{health.adaptive_backoff_multiplier}
            </div>
            <div className="text-xs text-muted mt-1">
              {health.consecutive_error_cycles} consecutive cycles with X errors. Resets on next clean cycle.
            </div>
          </div>
        </div>
      )}

      {/* Cookie freshness — banner after 30 days */}
      {cookie && cookie.needs_refresh && (
        <div className="glass p-4 border-lavender/40 bg-lavender/5 flex items-start gap-3">
          <Cookie className="text-lavender shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <div className="font-semibold text-lavender">
              {cookie.exists ? "Cookies aging — refresh recommended" : "No cookies — login required"}
            </div>
            <div className="text-xs text-muted mt-1">
              {cookie.exists && (<>Last refreshed {cookie.age_days} days ago. </>)}
              Run <code className="mono bg-black/60 px-1.5 py-0.5 rounded">$env:HEADLESS=&quot;false&quot;; python x_automation_bot.py login</code> to re-auth.
            </div>
          </div>
        </div>
      )}

      <section className="glass p-6 flex flex-col md:flex-row items-start md:items-center gap-6 justify-between">
        <div className="flex flex-col gap-3">
          <span
            className={cn(
              "inline-flex items-center self-start px-3 py-1 rounded-full border text-xs uppercase tracking-widest font-medium",
              statusStyle[s]
            )}
          >
            {s}
          </span>
          <div className="text-lg font-medium">{status?.current_action || "idle"}</div>
          <div className="text-xs text-muted">Last run: {timeAgo(status?.last_run)}</div>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted uppercase tracking-widest">Next cycle in</div>
          <Countdown to={status?.next_cycle_at} />
        </div>
      </section>

      <section className="flex gap-3 flex-wrap">
        <button
          onClick={() => handleControl(s === "paused" ? "resume" : "start")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-lavender text-black font-medium hover:bg-lavender/90 transition"
        >
          <Play size={16} /> {s === "paused" ? "Resume" : "Start"}
        </button>
        <button
          onClick={() => handleControl("pause")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-border hover:bg-white/5 transition"
        >
          <Pause size={16} /> Pause
        </button>
        <button
          onClick={() => handleControl("stop")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-rose-500/40 text-rose-300 hover:bg-rose-500/10 transition"
        >
          <Square size={16} /> Stop
        </button>
        <button
          onClick={() => {
            if (confirm("Skip the current cooldown and start a new cycle now?")) {
              handleControl("reset_cycle");
            }
          }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-lavender/40 text-lavender hover:bg-lavender/10 transition ml-auto"
          title="Skip the rest of the current wait/cycle and trigger a fresh cycle immediately"
        >
          <RotateCcw size={16} /> Reset Cycle
        </button>
      </section>

      <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard icon={MessageCircle} label="Total Tweets" value={stats?.total_tweets ?? 0} />
        <StatCard icon={MessagesSquare} label="Total Replies" value={stats?.total_replies ?? 0} />
        <StatCard icon={Heart} label="Total Likes" value={stats?.total_likes ?? 0} />
        <StatCard icon={UserPlus} label="Total Follows" value={stats?.total_follows ?? 0} />
        <StatCard icon={Cpu} label="LLM Calls Today" value={stats?.llm_calls_today ?? 0} />
      </section>

      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Activity</h2>
        {activity.length === 0 ? (
          <div className="text-sm text-muted">No activity yet. Once the bot runs, it will appear here.</div>
        ) : (
          <ul className="divide-y divide-border">
            {activity.map((a, i) => (
              <li key={i} className="py-3 flex gap-4 items-start">
                <span
                  className={cn(
                    "text-[10px] uppercase tracking-widest px-2 py-1 rounded shrink-0 mt-0.5",
                    a.type === "tweet" && "bg-lavender/15 text-lavender",
                    a.type === "reply" && "bg-emerald-500/15 text-emerald-300",
                    a.type === "follow" && "bg-amber-500/15 text-amber-300"
                  )}
                >
                  {a.type}
                </span>
                <p className="text-sm flex-1 line-clamp-2">{a.text}</p>
                <span className="text-xs text-muted shrink-0 mono">{timeAgo(a.ts)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
