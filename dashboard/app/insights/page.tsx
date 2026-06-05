"use client";

import useSWR from "swr";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AccountAnalytics,
  AnalyticsMetric,
  FollowerPoint,
  fetcher,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import {
  Activity,
  BadgeCheck,
  Bookmark,
  Eye,
  Gauge,
  Heart,
  MessageCircle,
  Repeat2,
  Share2,
  UserPlus,
  UserSearch,
  Zap,
} from "lucide-react";

const COLORS = { lavender: "#A78BFA", muted: "#8A8B97" };

const tooltipStyle = {
  background: "rgba(10,10,15,0.97)",
  border: "1px solid rgba(167,139,250,0.25)",
  borderRadius: 10,
  fontSize: 12,
};

// Display order + presentation for each scraped metric
const METRICS: { key: string; label: string; icon: any; accent: string }[] = [
  { key: "impressions", label: "Impressions", icon: Eye, accent: "#A78BFA" },
  { key: "engagement_rate", label: "Engagement rate", icon: Activity, accent: "#34D399" },
  { key: "engagements", label: "Engagements", icon: Zap, accent: "#FBBF24" },
  { key: "profile_visits", label: "Profile visits", icon: UserSearch, accent: "#38BDF8" },
  { key: "verified_followers", label: "Verified followers", icon: BadgeCheck, accent: "#A78BFA" },
  { key: "new_follows", label: "New follows", icon: UserPlus, accent: "#34D399" },
  { key: "replies", label: "Replies", icon: MessageCircle, accent: "#34D399" },
  { key: "likes", label: "Likes", icon: Heart, accent: "#F87171" },
  { key: "reposts", label: "Reposts", icon: Repeat2, accent: "#38BDF8" },
  { key: "bookmarks", label: "Bookmarks", icon: Bookmark, accent: "#FBBF24" },
  { key: "shares", label: "Shares", icon: Share2, accent: "#A78BFA" },
];

function deltaTone(delta: string | null | undefined): "up" | "down" | null {
  if (!delta) return null;
  if (delta.includes("↓") || delta.trim().startsWith("-")) return "down";
  return "up";
}

export default function InsightsPage() {
  const { data: analytics } = useSWR<AccountAnalytics>("/api/account_analytics", fetcher, {
    refreshInterval: 60000,
  });
  const { data: followers } = useSWR<FollowerPoint[]>("/api/follower_series", fetcher, {
    refreshInterval: 60000,
  });

  const metrics = analytics?.metrics || {};
  const hasMetrics = Object.keys(metrics).length > 0;

  const followerFmt = (followers || []).map((p) => ({
    ...p,
    label: new Date(p.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));
  const followerDelta =
    followerFmt.length >= 2 ? followerFmt[followerFmt.length - 1].count - followerFmt[0].count : null;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Gauge size={26} className="text-lavender" /> X Insights
          </h1>
          <p className="text-muted text-sm">
            Pulled live from your X analytics{analytics?.range ? ` · ${analytics.range}` : ""}.
          </p>
        </div>
        {analytics?.fetched_at && (
          <span className="text-xs text-muted glass pill px-3 py-1.5">
            updated {timeAgo(analytics.fetched_at)}
          </span>
        )}
      </header>

      {!hasMetrics ? (
        <div className="glass p-12 text-center">
          <Gauge size={28} className="text-muted/50 mx-auto mb-3" />
          <p className="text-sm text-muted max-w-md mx-auto">
            No analytics scraped yet. The bot reads your X analytics overview
            once per cycle (right after the account-health check). Check back
            after the next cycle completes.
          </p>
        </div>
      ) : (
        <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {METRICS.filter((m) => metrics[m.key]).map((m) => (
            <MetricCard key={m.key} label={m.label} icon={m.icon} accent={m.accent} metric={metrics[m.key]} />
          ))}
        </section>
      )}

      {/* Followers over time — from our own daily snapshots */}
      <section className="glass p-6">
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <h2 className="text-lg font-semibold">Followers over time</h2>
            <p className="text-xs text-muted">Recorded daily by the bot</p>
          </div>
          {followerFmt.length > 0 && (
            <div className="text-right">
              <div className="num text-2xl font-semibold tracking-tight text-lavender">
                {followerFmt[followerFmt.length - 1].count}
              </div>
              {followerDelta !== null && (
                <div className={cn("text-xs num", followerDelta >= 0 ? "text-emerald-300" : "text-rose-300")}>
                  {followerDelta >= 0 ? "+" : ""}
                  {followerDelta} in {followerFmt.length}d
                </div>
              )}
            </div>
          )}
        </div>
        {followerFmt.length < 2 ? (
          <div className="h-[200px] flex items-center justify-center text-sm text-muted">
            Need a couple days of data — the bot snapshots your follower count each cycle.
          </div>
        ) : (
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={followerFmt} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="followFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.lavender} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={COLORS.lavender} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} minTickGap={24} />
                <YAxis stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} width={42} domain={["dataMin - 2", "dataMax + 2"]} allowDecimals={false} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  itemStyle={{ color: "#e9e9ee" }}
                  labelStyle={{ color: "#fff", fontWeight: 600 }}
                  cursor={{ stroke: "rgba(167,139,250,0.3)" }}
                />
                <Area type="monotone" dataKey="count" name="followers" stroke={COLORS.lavender} strokeWidth={2.5} fill="url(#followFill)" dot={false} activeDot={{ r: 4, fill: COLORS.lavender, stroke: "#000", strokeWidth: 2 }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>

      <p className="text-xs text-muted/70 text-center">
        Read from <code className="mono">x.com/i/account_analytics</code> using the bot&apos;s own logged-in session — no paid API.
      </p>
    </div>
  );
}

function MetricCard({
  label,
  icon: Icon,
  accent,
  metric,
}: {
  label: string;
  icon: any;
  accent: string;
  metric: AnalyticsMetric;
}) {
  const tone = deltaTone(metric.delta);
  return (
    <div className="glass p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{label}</div>
        <div className="w-8 h-8 rounded-xl flex items-center justify-center" style={{ background: `${accent}1f` }}>
          <Icon size={15} style={{ color: accent }} />
        </div>
      </div>
      <div className="mt-3 flex items-end gap-2">
        <div className="text-[2rem] leading-none font-semibold tracking-tight num">
          {metric.value}
          {metric.total && <span className="text-muted text-lg"> / {metric.total}</span>}
        </div>
      </div>
      {metric.delta && tone && (
        <div
          className={cn(
            "mt-2 inline-flex items-center gap-0.5 text-[11px] font-medium px-1.5 py-0.5 rounded-md num",
            tone === "up" ? "text-emerald-300 bg-emerald-500/10" : "text-rose-300 bg-rose-500/10"
          )}
        >
          {metric.delta}
        </div>
      )}
    </div>
  );
}
