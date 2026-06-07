"use client";

import useSWR from "swr";
import { useState } from "react";
import { toast } from "sonner";
import { EngagementPod, fetcher, toggleEngagementPod } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { AlertTriangle, ExternalLink, Rocket } from "lucide-react";

export default function BoostPage() {
  const { data, mutate } = useSWR<EngagementPod>("/api/engagement_pod", fetcher, {
    refreshInterval: 10000,
  });
  const [saving, setSaving] = useState(false);
  const enabled = data?.enabled ?? false;
  const history = data?.history ?? [];

  async function onToggle() {
    setSaving(true);
    try {
      const res = await toggleEngagementPod(!enabled);
      toast.success(res.enabled ? "Boost mode ON" : "Boost mode OFF");
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Toggle failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <header>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Rocket size={26} className="text-lavender" /> Boost
        </h1>
        <p className="text-muted text-sm">
          Auto-replies to fresh “comment X / let’s connect” engagement-pod posts to pull
          follow-backs and impressions. Off by default.
        </p>
      </header>

      {/* The toggle */}
      <div className={cn("glass p-6 flex items-center justify-between gap-4", enabled && "glass-accent")}>
        <div>
          <div className="text-lg font-semibold flex items-center gap-2">
            Boost mode
            <span
              className={cn(
                "pill text-xs px-2.5 py-0.5 font-medium",
                enabled ? "bg-emerald-500/15 text-emerald-300" : "bg-white/5 text-muted"
              )}
            >
              {enabled ? "ON" : "OFF"}
            </span>
          </div>
          <p className="text-sm text-muted mt-1">
            {enabled
              ? `Running ~6 pod replies per cycle. ${data?.total ?? 0} sent so far.`
              : "Toggle on to start replying to engagement-pod posts each cycle."}
          </p>
        </div>
        <button
          onClick={onToggle}
          disabled={saving}
          role="switch"
          aria-checked={enabled}
          className={cn(
            "relative w-14 h-8 rounded-full transition-colors shrink-0 disabled:opacity-50",
            enabled ? "bg-lavender" : "bg-white/10"
          )}
        >
          <span
            className={cn(
              "absolute top-1 w-6 h-6 rounded-full bg-white transition-transform",
              enabled ? "translate-x-7" : "translate-x-1"
            )}
          />
        </button>
      </div>

      {/* Honest heads-up */}
      <div className="glass p-4 border-amber-500/30 bg-amber-500/5 flex items-start gap-3">
        <AlertTriangle size={16} className="text-amber-300 shrink-0 mt-0.5" />
        <div className="text-xs text-muted leading-relaxed">
          <span className="text-amber-300 font-medium">Heads up:</span> these are
          follow-for-follow accounts — great for raw follower/impression numbers, but they
          rarely engage your real content, which can dilute your engagement rate over time.
          Boost is reply-only (never mass-follows), uses the exact word each post asks for
          (varied, human-looking), and counts toward your daily action ceiling. Use it as a
          supplement to the real growth engine, not a replacement.
        </div>
      </div>

      {/* History */}
      <section className="glass p-6">
        <h2 className="text-lg font-semibold mb-1">Recent pod replies</h2>
        <p className="text-xs text-muted mb-4">{data?.total ?? 0} total</p>
        {history.length === 0 ? (
          <div className="text-sm text-muted">
            {enabled ? "No pod replies yet — they’ll appear here after the next cycle." : "Boost is off."}
          </div>
        ) : (
          <ul className="space-y-2">
            {history.map((h, i) => (
              <li key={i} className="glass p-4">
                <p className="text-sm">
                  replied <span className="text-lavender">“{h.reply}”</span>
                </p>
                {h.original_tweet_text && (
                  <p className="text-xs text-muted mt-1.5 line-clamp-2">↪ {h.original_tweet_text}</p>
                )}
                <div className="flex items-center justify-between mt-2 text-xs text-muted">
                  <a
                    href={h.original_tweet_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-lavender hover:underline"
                  >
                    <ExternalLink size={12} /> original
                  </a>
                  <span className="num">{timeAgo(h.posted_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
