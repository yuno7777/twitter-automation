"use client";

import useSWR from "swr";
import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  PolarAngleAxis,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AnalyticsResponse, fetcher, OptimalHoursResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  ArrowDownRight,
  ArrowUpRight,
  Heart,
  MessageCircle,
  Repeat2,
  Send,
  TrendingUp,
  UserPlus,
} from "lucide-react";

const RANGES = [7, 14, 30] as const;

const COLORS = {
  lavender: "#A78BFA",
  emerald: "#34D399",
  rose: "#F87171",
  amber: "#FBBF24",
  sky: "#38BDF8",
  muted: "#8b8b94",
};

const tooltipStyle = {
  background: "rgba(10,10,15,0.95)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 8px 30px rgba(0,0,0,0.5)",
};

const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function deltaPct(daily: { [k: string]: number | string }[], key: string): number | null {
  const n = daily.length;
  if (n < 2) return null;
  const mid = Math.floor(n / 2);
  const older = daily.slice(0, mid).reduce((s, d) => s + (Number(d[key]) || 0), 0);
  const recent = daily.slice(mid).reduce((s, d) => s + (Number(d[key]) || 0), 0);
  if (older === 0) return recent > 0 ? 100 : 0;
  return ((recent - older) / older) * 100;
}

export default function AnalyticsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(14);
  const { data } = useSWR<AnalyticsResponse>(`/api/analytics?days=${days}`, fetcher, {
    refreshInterval: 30000,
  });
  const { data: optimal } = useSWR<OptimalHoursResponse>("/api/optimal_hours", fetcher, {
    refreshInterval: 60000,
  });

  if (!data) return <div className="text-muted text-sm">Loading analytics…</div>;

  const { daily, hourly, window_totals, top_tweets, totals, cycles_run } = data;

  const dailyFmt = daily.map((d) => ({
    ...d,
    total: d.tweets + d.replies + d.likes + d.follows,
    label: new Date(d.date + "T00:00:00").toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
  }));

  // Day-of-week aggregation
  const dow = DOW.map((name) => ({ name, total: 0 }));
  daily.forEach((d) => {
    const wd = new Date(d.date + "T00:00:00").getDay();
    dow[wd].total += d.tweets + d.replies + d.likes + d.follows;
  });
  const peakDowIdx = dow.reduce((best, d, i, arr) => (d.total > arr[best].total ? i : best), 0);

  // Hourly with peak highlight
  const peakHour = hourly.reduce((best, h, i, arr) => (h.count > arr[best].count ? i : best), 0);

  // Action composition
  const composition = [
    { name: "Tweets", value: window_totals.tweets, fill: COLORS.lavender },
    { name: "Replies", value: window_totals.replies, fill: COLORS.emerald },
    { name: "Likes", value: window_totals.likes, fill: COLORS.rose },
    { name: "Follows", value: window_totals.follows, fill: COLORS.amber },
  ].filter((c) => c.value > 0);

  const totalActions =
    window_totals.tweets + window_totals.replies + window_totals.likes + window_totals.follows;
  const replyRate = totalActions ? Math.round((window_totals.replies / totalActions) * 100) : 0;

  const cards = [
    { label: "Tweets", value: window_totals.tweets, icon: Send, color: COLORS.lavender, delta: deltaPct(daily, "tweets") },
    { label: "Replies", value: window_totals.replies, icon: MessageCircle, color: COLORS.emerald, delta: deltaPct(daily, "replies") },
    { label: "Likes", value: window_totals.likes, icon: Heart, color: COLORS.rose, delta: deltaPct(daily, "likes") },
    { label: "Follows", value: window_totals.follows, icon: UserPlus, color: COLORS.amber, delta: deltaPct(daily, "follows") },
  ];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
          <p className="text-muted text-sm">Activity & engagement over the last {days} days.</p>
        </div>
        <div className="flex gap-1 glass p-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDays(r)}
              className={cn(
                "px-3 py-1.5 rounded-md text-xs transition",
                days === r ? "bg-lavender text-black" : "text-muted hover:text-white"
              )}
            >
              {r}d
            </button>
          ))}
        </div>
      </header>

      {/* KPI cards with delta badges */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => (
          <KpiCard key={c.label} {...c} avg={(c.value / days).toFixed(1)} />
        ))}
      </section>

      {/* Hero area + most-active-day */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass p-6 lg:col-span-2">
          <div className="flex items-baseline justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold">Activity trend</h2>
              <p className="text-xs text-muted">Total actions per day</p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-semibold mono text-lavender">{totalActions}</div>
              <div className="text-[10px] text-muted uppercase tracking-widest">total actions</div>
            </div>
          </div>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={dailyFmt} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={COLORS.lavender} stopOpacity={0.45} />
                    <stop offset="100%" stopColor={COLORS.lavender} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} minTickGap={20} />
                <YAxis stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={36} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ stroke: "rgba(167,139,250,0.3)" }} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke={COLORS.lavender}
                  strokeWidth={2.5}
                  fill="url(#areaFill)"
                  dot={false}
                  activeDot={{ r: 4, fill: COLORS.lavender, stroke: "#000", strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass p-6">
          <h2 className="text-lg font-semibold">Most active day</h2>
          <p className="text-xs text-muted mb-4">By day of week</p>
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dow} margin={{ top: 8, right: 0, left: -28, bottom: 0 }}>
                <XAxis dataKey="name" stroke={COLORS.muted} fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={32} />
                <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(167,139,250,0.06)" }} />
                <Bar dataKey="total" radius={[6, 6, 0, 0]}>
                  {dow.map((_, i) => (
                    <Cell key={i} fill={i === peakDowIdx ? COLORS.lavender : "rgba(167,139,250,0.18)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Composition donut + reply-rate gauge + breakdown */}
      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="glass p-6">
          <h2 className="text-lg font-semibold mb-1">Action mix</h2>
          <p className="text-xs text-muted mb-2">How the bot spends its actions</p>
          <div className="h-[200px] relative">
            {composition.length === 0 ? (
              <Empty />
            ) : (
              <>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={composition}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={58}
                      outerRadius={82}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {composition.map((c, i) => (
                        <Cell key={i} fill={c.fill} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <div className="text-2xl font-semibold mono">{totalActions}</div>
                  <div className="text-[10px] text-muted uppercase tracking-widest">actions</div>
                </div>
              </>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 mt-3">
            {composition.map((c) => (
              <div key={c.name} className="flex items-center gap-2 text-xs">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: c.fill }} />
                <span className="text-muted">{c.name}</span>
                <span className="ml-auto mono">{c.value}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass p-6 flex flex-col">
          <h2 className="text-lg font-semibold mb-1">Reply rate</h2>
          <p className="text-xs text-muted mb-2">Share of actions that are replies — your top growth lever</p>
          <div className="h-[200px] relative flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <RadialBarChart
                innerRadius="72%"
                outerRadius="100%"
                data={[{ name: "reply", value: replyRate, fill: COLORS.lavender }]}
                startAngle={220}
                endAngle={-40}
              >
                <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
                <RadialBar background={{ fill: "rgba(255,255,255,0.06)" }} dataKey="value" cornerRadius={20} angleAxisId={0} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <div className="text-4xl font-bold mono text-lavender">{replyRate}%</div>
              <div className="text-[11px] text-muted mt-1">{window_totals.replies} replies</div>
            </div>
          </div>
        </div>

        <div className="glass p-6">
          <h2 className="text-lg font-semibold mb-3">Per-day average</h2>
          <div className="space-y-3">
            <MiniStat label="Tweets" value={(window_totals.tweets / days).toFixed(1)} color={COLORS.lavender} />
            <MiniStat label="Replies" value={(window_totals.replies / days).toFixed(1)} color={COLORS.emerald} />
            <MiniStat label="Likes" value={(window_totals.likes / days).toFixed(1)} color={COLORS.rose} />
            <MiniStat label="Follows" value={(window_totals.follows / days).toFixed(1)} color={COLORS.amber} />
            <div className="border-t border-border pt-3 flex items-center justify-between">
              <span className="text-xs text-muted">Cycles run</span>
              <span className="mono font-semibold">{cycles_run}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Hourly */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold">When the bot is active</h2>
        <p className="text-xs text-muted mb-4">Total actions per hour of day (local time)</p>
        <div className="h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hourly} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
              <XAxis dataKey="hour" stroke={COLORS.muted} fontSize={10} tickLine={false} axisLine={false} interval={1} tickFormatter={(h) => `${h}`} />
              <YAxis stroke={COLORS.muted} fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} width={32} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(167,139,250,0.06)" }} labelFormatter={(h) => `${h}:00`} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {hourly.map((_, i) => (
                  <Cell key={i} fill={i === peakHour ? COLORS.lavender : "rgba(167,139,250,0.2)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Optimal hours */}
      {optimal && optimal.recommended_peak_hours.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-1">Optimal posting hours</h2>
          <p className="text-xs text-muted mb-4">
            Auto-detected from your own engagement ({optimal.sample_size} tweets). Update{" "}
            <code className="mono">PEAK_HOURS</code> in <code className="mono">.env</code> to apply.
          </p>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-xs text-muted uppercase tracking-widest mb-2">Current</div>
              <div className="flex flex-wrap gap-1.5">
                {optimal.current_peak_hours.map((h) => (
                  <span key={h} className="mono px-2 py-0.5 rounded bg-white/5 border border-border text-xs">{h}:00</span>
                ))}
              </div>
            </div>
            <div>
              <div className="text-xs text-emerald-300 uppercase tracking-widest mb-2">Recommended</div>
              <div className="flex flex-wrap gap-1.5">
                {optimal.recommended_peak_hours.map((h) => (
                  <span key={h} className="mono px-2 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-xs">{h}:00</span>
                ))}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Top tweets */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-1">Top-performing tweets</h2>
        <p className="text-xs text-muted mb-4">Scraped each cycle — the LLM uses these as a reference to write more like them.</p>
        {top_tweets.length === 0 ? (
          <Empty label="No data yet. The bot scrapes engagement after its first full cycle." />
        ) : (
          <ul className="space-y-3">
            {top_tweets.map((t, i) => (
              <li key={i} className="flex items-start gap-4 border-b border-border last:border-0 pb-3 last:pb-0">
                <div className="shrink-0 w-14 text-center">
                  <div className="text-lavender text-2xl font-semibold mono flex items-center justify-center gap-1">
                    <Heart size={14} className="text-rose-300" /> {t.likes}
                  </div>
                </div>
                <p className="text-sm flex-1 leading-relaxed">{t.text}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Lifetime */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-4">All time</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <LifetimeStat icon={Send} label="Tweets" value={totals.total_tweets} />
          <LifetimeStat icon={MessageCircle} label="Replies" value={totals.total_replies} />
          <LifetimeStat icon={Heart} label="Likes" value={totals.total_likes ?? 0} />
          <LifetimeStat icon={UserPlus} label="Follows" value={totals.total_follows} />
          <LifetimeStat icon={Repeat2} label="Cycles" value={cycles_run} />
        </div>
      </section>
    </div>
  );
}

function KpiCard({
  label,
  value,
  avg,
  icon: Icon,
  color,
  delta,
}: {
  label: string;
  value: number;
  avg: string;
  icon: any;
  color: string;
  delta: number | null;
}) {
  const up = (delta ?? 0) >= 0;
  return (
    <div className="glass p-5">
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted">{label}</div>
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: `${color}1f` }}
        >
          <Icon size={15} style={{ color }} />
        </div>
      </div>
      <div className="mt-2 flex items-end gap-2">
        <div className="text-3xl font-semibold mono">{value}</div>
        {delta !== null && (
          <div
            className={cn(
              "mb-1 flex items-center gap-0.5 text-[11px] font-medium px-1.5 py-0.5 rounded-md",
              up ? "text-emerald-300 bg-emerald-500/10" : "text-rose-300 bg-rose-500/10"
            )}
          >
            {up ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
            {Math.abs(delta).toFixed(0)}%
          </div>
        )}
      </div>
      <div className="text-xs text-muted mt-1">{avg}/day · vs first half</div>
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: color }} />
        <span className="text-xs text-muted">{label}</span>
      </div>
      <span className="mono text-sm font-medium">{value}</span>
    </div>
  );
}

function LifetimeStat({ icon: Icon, label, value }: { icon: any; label: string; value: number | string }) {
  return (
    <div className="flex items-center gap-3">
      <div className="w-9 h-9 rounded-lg bg-lavender/10 flex items-center justify-center shrink-0">
        <Icon size={16} className="text-lavender" />
      </div>
      <div>
        <div className="text-xl font-semibold mono leading-tight">{value}</div>
        <div className="text-[11px] text-muted uppercase tracking-widest">{label}</div>
      </div>
    </div>
  );
}

function Empty({ label = "No data yet." }: { label?: string }) {
  return (
    <div className="h-full flex items-center justify-center text-center text-muted text-sm">
      <div className="flex flex-col items-center gap-2">
        <TrendingUp size={20} className="text-muted/50" />
        {label}
      </div>
    </div>
  );
}
