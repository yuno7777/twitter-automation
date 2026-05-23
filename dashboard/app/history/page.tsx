"use client";

import useSWR from "swr";
import { useState } from "react";
import {
  fetcher,
  FollowHistoryItem,
  FollowUpHistoryItem,
  QuoteHistoryItem,
  ReplyHistoryItem,
  TweetHistoryItem,
} from "@/lib/api";
import { cn, formatLocalTime } from "@/lib/utils";
import { ExternalLink } from "lucide-react";

const TABS = ["tweets", "replies", "quotes", "follow_ups", "follows"] as const;
type Tab = (typeof TABS)[number];

export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>("tweets");
  const { data: tweets } = useSWR<TweetHistoryItem[]>("/api/history/tweets", fetcher, { refreshInterval: 10000 });
  const { data: replies } = useSWR<ReplyHistoryItem[]>("/api/history/replies", fetcher, { refreshInterval: 10000 });
  const { data: quotes } = useSWR<QuoteHistoryItem[]>("/api/history/quotes", fetcher, { refreshInterval: 10000 });
  const { data: followUps } = useSWR<FollowUpHistoryItem[]>("/api/history/follow_ups", fetcher, { refreshInterval: 10000 });
  const { data: follows } = useSWR<FollowHistoryItem[]>("/api/history/follows", fetcher, { refreshInterval: 10000 });

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">History</h1>
        <p className="text-muted text-sm">Everything the bot has posted, replied to, and followed.</p>
      </header>

      <div className="flex gap-2 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2 text-sm capitalize transition",
              tab === t
                ? "border-b-2 border-lavender text-lavender"
                : "text-muted hover:text-white"
            )}
          >
            {t.replace("_", "-")}
          </button>
        ))}
      </div>

      {tab === "tweets" && <TweetsTable rows={tweets || []} />}
      {tab === "replies" && <RepliesTable rows={replies || []} />}
      {tab === "quotes" && <QuotesTable rows={quotes || []} />}
      {tab === "follow_ups" && <FollowUpsTable rows={followUps || []} />}
      {tab === "follows" && <FollowsTable rows={follows || []} />}
    </div>
  );
}

function QuotesTable({ rows }: { rows: QuoteHistoryItem[] }) {
  if (rows.length === 0) return <Empty label="No quote-tweets yet." />;
  return (
    <ul className="space-y-2">
      {rows.map((q, i) => (
        <li key={i} className="glass p-4">
          <p className="text-sm">{q.quote_text}</p>
          {q.original_tweet_text && (
            <p className="text-xs text-muted mt-2 line-clamp-2 italic">
              quoting: {q.original_tweet_text}
              {q.original_likes !== undefined && (
                <span className="ml-2 text-lavender mono">({q.original_likes} likes)</span>
              )}
            </p>
          )}
          <div className="flex items-center justify-between mt-2 text-xs text-muted">
            <a
              href={q.original_tweet_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-lavender hover:underline"
            >
              <ExternalLink size={12} /> original
            </a>
            <span className="mono">{formatLocalTime(q.posted_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function FollowUpsTable({ rows }: { rows: FollowUpHistoryItem[] }) {
  if (rows.length === 0) return <Empty label="No follow-ups yet." />;
  return (
    <ul className="space-y-2">
      {rows.map((f, i) => (
        <li key={i} className="glass p-4">
          <p className="text-xs text-muted mb-1">you posted:</p>
          <p className="text-sm text-white/70">{f.your_tweet}</p>
          <p className="text-xs text-muted mt-3 mb-1">they replied:</p>
          <p className="text-sm text-white/70 italic">{f.their_reply}</p>
          <p className="text-xs text-lavender mt-3 mb-1">your follow-up:</p>
          <p className="text-sm">{f.your_followup}</p>
          <div className="flex items-center justify-between mt-3 text-xs text-muted">
            <a
              href={f.thread_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-lavender hover:underline"
            >
              <ExternalLink size={12} /> thread
            </a>
            <span className="mono">{formatLocalTime(f.posted_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function ExpandableRow({ preview, full, meta }: { preview: string; full: string; meta: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="glass p-4 cursor-pointer" onClick={() => setOpen((v) => !v)}>
      <div className="flex items-start gap-4">
        <p className="flex-1 text-sm">{open ? full : preview}</p>
        <div className="text-xs text-muted shrink-0 text-right">{meta}</div>
      </div>
    </li>
  );
}

function TweetsTable({ rows }: { rows: TweetHistoryItem[] }) {
  if (rows.length === 0) return <Empty label="No tweets yet." />;
  return (
    <ul className="space-y-2">
      {rows.map((t, i) => (
        <ExpandableRow
          key={i}
          preview={t.text.length > 80 ? t.text.slice(0, 80) + "…" : t.text}
          full={t.text}
          meta={
            <>
              <div className="mono">{formatLocalTime(t.posted_at)}</div>
              {t.news_title && <div className="text-muted/80 line-clamp-1 max-w-[260px]">{t.news_title}</div>}
            </>
          }
        />
      ))}
    </ul>
  );
}

function RepliesTable({ rows }: { rows: ReplyHistoryItem[] }) {
  if (rows.length === 0) return <Empty label="No replies yet." />;
  return (
    <ul className="space-y-2">
      {rows.map((r, i) => (
        <li key={i} className="glass p-4">
          <p className="text-sm">{r.reply_text}</p>
          {r.original_tweet_text && (
            <p className="text-xs text-muted mt-2 line-clamp-2">↪ {r.original_tweet_text}</p>
          )}
          <div className="flex items-center justify-between mt-2 text-xs text-muted">
            <a
              href={r.original_tweet_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-lavender hover:underline"
            >
              <ExternalLink size={12} /> View original
            </a>
            <span className="mono">{formatLocalTime(r.posted_at)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

function FollowsTable({ rows }: { rows: FollowHistoryItem[] }) {
  if (rows.length === 0) return <Empty label="No follows yet." />;
  return (
    <ul className="space-y-2">
      {rows.map((f, i) => (
        <li key={i} className="glass p-4 flex items-center justify-between">
          <div>
            <a
              href={`https://x.com/${f.username}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-lavender font-medium hover:underline"
            >
              @{f.username}
            </a>
            {f.follower_count && (
              <span className="text-xs text-muted ml-3">{f.follower_count} followers</span>
            )}
          </div>
          <span className="text-xs text-muted mono">{formatLocalTime(f.followed_at)}</span>
        </li>
      ))}
    </ul>
  );
}

function Empty({ label }: { label: string }) {
  return <div className="glass p-8 text-center text-muted text-sm">{label}</div>;
}
