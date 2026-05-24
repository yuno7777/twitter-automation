"use client";

import useSWR from "swr";
import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";
import { AnalyticsResponse, fetcher, OptimalHoursResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const RANGES = [7, 14, 30] as const;

export default function AnalyticsPage() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(14);
  const { data } = useSWR<AnalyticsResponse>(
    `/api/analytics?days=${days}`,
    fetcher,
    { refreshInterval: 30000 }
  );
  const { data: optimal } = useSWR<OptimalHoursResponse>("/api/optimal_hours", fetcher, { refreshInterval: 60000 });

  if (!data) {
    return <div className="text-muted text-sm">Loading analytics…</div>;
  }

  const { daily, hourly, window_totals, busiest_day, top_tweets, totals, cycles_run } = data;

  // Format dates as "May 14"
  const dailyFmt = daily.map((d) => ({
    ...d,
    label: new Date(d.date + "T00:00:00").toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
  }));

  const maxHour = Math.max(...hourly.map((h) => h.count), 1);

  const avg = {
    tweets: (window_totals.tweets / days).toFixed(1),
    replies: (window_totals.replies / days).toFixed(1),
    likes: (window_totals.likes / days).toFixed(1),
    follows: (window_totals.follows / days).toFixed(1),
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Analytics</h1>
          <p className="text-muted text-sm">
            What the bot has been doing over the last {days} days.
          </p>
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

      {/* Summary cards */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard label="Tweets" total={window_totals.tweets} avg={avg.tweets} color="text-lavender" />
        <SummaryCard label="Replies" total={window_totals.replies} avg={avg.replies} color="text-emerald-300" />
        <SummaryCard label="Likes" total={window_totals.likes} avg={avg.likes} color="text-rose-300" />
        <SummaryCard label="Follows" total={window_totals.follows} avg={avg.follows} color="text-amber-300" />
      </section>

      {/* Daily stacked bar */}
      <section className="glass p-6">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="text-lg font-semibold">Daily activity</h2>
          {busiest_day && (
            <span className="text-xs text-muted">
              Busiest day: <span className="text-white">{busiest_day}</span>
            </span>
          )}
        </div>
        <div className="h-[280px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={dailyFmt} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="label" stroke="#8b8b94" fontSize={11} tickLine={false} axisLine={false} />
              <YAxis stroke="#8b8b94" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: "rgba(10,10,15,0.95)",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 10,
                  fontSize: 12,
                }}
                cursor={{ fill: "rgba(167,139,250,0.08)" }}
              />
              <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} iconType="circle" />
              <Bar dataKey="tweets" stackId="a" fill="#A78BFA" radius={[0, 0, 0, 0]} />
              <Bar dataKey="replies" stackId="a" fill="#34D399" />
              <Bar dataKey="likes" stackId="a" fill="#F87171" />
              <Bar dataKey="follows" stackId="a" fill="#FBBF24" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Hourly heatmap */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-1">When the bot is active</h2>
        <p className="text-xs text-muted mb-4">Total actions per hour of day (local time)</p>
        <div className="grid grid-cols-24 gap-1" style={{ gridTemplateColumns: "repeat(24, minmax(0,1fr))" }}>
          {hourly.map((h) => {
            const intensity = h.count / maxHour;
            return (
              <div key={h.hour} className="flex flex-col items-center gap-1.5">
                <div
                  className="w-full rounded-sm transition"
                  style={{
                    height: `${24 + intensity * 64}px`,
                    background: `rgba(167,139,250,${0.12 + intensity * 0.78})`,
                    boxShadow: intensity > 0.5 ? "0 0 12px rgba(124,58,237,0.3)" : "none",
                  }}
                  title={`${h.hour}:00 — ${h.count} actions`}
                />
                <span className="text-[9px] text-muted mono">{h.hour}</span>
              </div>
            );
          })}
        </div>
      </section>

      {/* Optimal posting hours — auto-detected from engagement */}
      {optimal && optimal.recommended_peak_hours.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-1">Optimal posting hours</h2>
          <p className="text-xs text-muted mb-4">
            Auto-detected from your own engagement data ({optimal.sample_size} tweets analyzed). Update <code className="mono">PEAK_HOURS</code> in <code className="mono">.env</code> to apply.
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
        <h2 className="text-lg font-semibold mb-1">Your top-performing tweets</h2>
        <p className="text-xs text-muted mb-4">
          Scraped from your profile each cycle. The LLM uses these as a reference to write more like them.
        </p>
        {top_tweets.length === 0 ? (
          <div className="text-sm text-muted">
            No data yet. The bot scrapes engagement after its first full cycle.
          </div>
        ) : (
          <ul className="space-y-3">
            {top_tweets.map((t, i) => (
              <li key={i} className="flex items-start gap-4 border-b border-border last:border-0 pb-3 last:pb-0">
                <div className="shrink-0 w-12 text-center">
                  <div className="text-lavender text-2xl font-semibold mono">{t.likes}</div>
                  <div className="text-[10px] text-muted uppercase tracking-widest">likes</div>
                </div>
                <p className="text-sm flex-1 leading-relaxed">{t.text}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Lifetime totals */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-4">All time</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-center">
          <Stat label="Tweets" value={totals.total_tweets} />
          <Stat label="Replies" value={totals.total_replies} />
          <Stat label="Likes" value={totals.total_likes ?? 0} />
          <Stat label="Follows" value={totals.total_follows} />
          <Stat label="Cycles run" value={cycles_run} />
        </div>
      </section>
    </div>
  );
}

function SummaryCard({
  label,
  total,
  avg,
  color,
}: {
  label: string;
  total: number;
  avg: string;
  color: string;
}) {
  return (
    <div className="glass p-5">
      <div className="text-xs text-muted uppercase tracking-widest">{label}</div>
      <div className={cn("text-3xl font-semibold mono mt-2", color)}>{total}</div>
      <div className="text-xs text-muted mt-1">{avg}/day avg</div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div className="text-2xl font-semibold mono">{value}</div>
      <div className="text-xs text-muted uppercase tracking-widest mt-1">{label}</div>
    </div>
  );
}
