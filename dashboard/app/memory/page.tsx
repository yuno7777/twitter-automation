"use client";

import useSWR from "swr";
import { ExternalLink, Star } from "lucide-react";
import { fetcher, MemoryResponse } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";

export default function MemoryPage() {
  const { data } = useSWR<MemoryResponse>("/api/memory", fetcher, { refreshInterval: 15000 });
  if (!data) return <div className="text-muted text-sm">Loading bot memory…</div>;

  const s = data.last_strategy;

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Bot Memory</h1>
        <p className="text-muted text-sm">
          What the bot is currently thinking about. Re-synthesized each cycle.
          {data.last_strategy_at && (
            <> Last strategy: <span className="text-white">{timeAgo(data.last_strategy_at)}</span></>
          )}
        </p>
      </header>

      {!s && (
        <div className="glass p-8 text-center text-muted text-sm">
          No strategy yet. The bot generates one at the start of every cycle.
        </div>
      )}

      {s && (
        <>
          {/* Live trending terms extracted from signals */}
          {data.trending_terms.length > 0 && (
            <section className="glass p-6">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-semibold">Live trending right now</h2>
                <span className="text-xs text-muted">extracted from GitHub + HN + Reddit</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {data.trending_terms.map((t, i) => (
                  <span key={i} className="px-3 py-1.5 rounded-full bg-gradient-to-r from-lavender/20 to-lavender-deep/20 border border-lavender/40 text-white text-sm font-medium">
                    {t}
                  </span>
                ))}
              </div>
            </section>
          )}

          {/* Current strategy — what it will search this cycle */}
          <section className="glass p-6 space-y-4">
            <h2 className="text-lg font-semibold">Current strategy</h2>
            <QueryList label="Reply searches" color="text-emerald-300" items={s.reply_queries} />
            <QueryList label="Like searches" color="text-rose-300" items={s.like_queries} />
            <QueryList label="Follow searches" color="text-amber-300" items={s.follow_queries} />
          </section>

          {/* Tweet topics it'll pull from */}
          {s.tweet_topics.length > 0 && (
            <section className="glass p-6">
              <h2 className="text-lg font-semibold mb-3">Tweet angles queued</h2>
              <ul className="space-y-3">
                {s.tweet_topics.map((t, i) => (
                  <li key={i} className="border-b border-border last:border-0 pb-3 last:pb-0">
                    <p className="text-sm text-white">{t.angle}</p>
                    <p className="text-xs text-muted mt-1.5">{t.context}</p>
                    {t.source_url && (
                      <a
                        href={t.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-lavender inline-flex items-center gap-1 mt-1.5 hover:underline"
                      >
                        <ExternalLink size={12} /> source
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Trending GitHub repos */}
          {s.github_repos_to_mention.length > 0 && (
            <section className="glass p-6">
              <h2 className="text-lg font-semibold mb-3">GitHub repos on radar</h2>
              <ul className="space-y-3">
                {s.github_repos_to_mention.map((r, i) => (
                  <li key={i} className="flex items-start gap-4 border-b border-border last:border-0 pb-3 last:pb-0">
                    <div className="shrink-0 flex items-center gap-1 text-amber-300 mono text-sm">
                      <Star size={14} fill="currentColor" /> {r.stars}
                    </div>
                    <div className="flex-1">
                      <a
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-lavender font-medium hover:underline mono text-sm"
                      >
                        {r.name}
                      </a>
                      <p className="text-xs text-muted mt-1">{r.why}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {/* Queued trends */}
      {data.trends_to_explore_later.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-3">Trends queued for later</h2>
          <div className="flex flex-wrap gap-2">
            {data.trends_to_explore_later.map((t, i) => (
              <span key={i} className="px-2.5 py-1 rounded-full bg-lavender/10 border border-lavender/30 text-lavender text-xs">
                {t}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Long-term topic memory */}
      {data.topics_seen.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-3">Topics covered so far</h2>
          <div className="flex flex-wrap gap-2">
            {data.topics_seen.map((t, i) => (
              <span key={i} className="px-2.5 py-1 rounded-full bg-white/5 border border-border text-muted text-xs">
                {t}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Repos already tweeted about */}
      {data.repos_tracked.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-3">Repos already tweeted</h2>
          <ul className="text-xs text-muted space-y-1 mono">
            {data.repos_tracked.slice().reverse().map((r, i) => (
              <li key={i}>
                <span className="text-white">{r.name}</span> · {timeAgo(r.ts)}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Recent search log — debugging signal */}
      {data.recent_queries.length > 0 && (
        <section className="glass p-6">
          <h2 className="text-lg font-semibold mb-3">Recent searches</h2>
          <ul className="text-xs space-y-1 mono">
            {data.recent_queries.slice().reverse().map((q, i) => (
              <li key={i} className="flex items-center justify-between gap-4 py-1 border-b border-border last:border-0">
                <div className="flex items-center gap-3">
                  <span className={cn(
                    "text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded shrink-0",
                    q.role === "reply" && "bg-emerald-500/15 text-emerald-300",
                    q.role === "like" && "bg-rose-500/15 text-rose-300",
                    q.role === "follow" && "bg-amber-500/15 text-amber-300",
                  )}>{q.role}</span>
                  <span className="text-white">{q.query}</span>
                </div>
                <div className="text-muted shrink-0">
                  {q.candidate_count} results · {timeAgo(q.ts)}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function QueryList({ label, color, items }: { label: string; color: string; items: string[] }) {
  return (
    <div>
      <div className={cn("text-xs uppercase tracking-widest mb-2", color)}>{label}</div>
      <div className="flex flex-wrap gap-2">
        {items.length === 0 ? (
          <span className="text-xs text-muted">(none)</span>
        ) : items.map((q, i) => (
          <span key={i} className="px-2.5 py-1 rounded-full bg-white/5 border border-border text-xs mono">
            {q}
          </span>
        ))}
      </div>
    </div>
  );
}
