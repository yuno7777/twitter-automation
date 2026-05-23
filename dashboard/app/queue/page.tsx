"use client";

import useSWR from "swr";
import { useState } from "react";
import { Check, X, Pencil, ExternalLink, ThumbsUp } from "lucide-react";
import { fetcher, DraftItem, approveDraft, rejectDraft, editDraft } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { toast } from "sonner";

export default function QueuePage() {
  const { data, mutate } = useSWR<DraftItem[]>("/api/queue", fetcher, { refreshInterval: 15000 });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const pending = (data || []).filter((d) => !d.approved);
  const approved = (data || []).filter((d) => d.approved);

  async function handleApprove(d: DraftItem) {
    try {
      await approveDraft(d.id);
      toast.success("Approved — will post next peak hour");
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Approve failed");
    }
  }

  async function handleReject(d: DraftItem) {
    if (!confirm("Reject this draft?")) return;
    try {
      await rejectDraft(d.id);
      toast.success("Rejected");
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Reject failed");
    }
  }

  async function handleSaveEdit(d: DraftItem) {
    try {
      await editDraft(d.id, editText);
      toast.success("Saved");
      setEditingId(null);
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Edit failed");
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Draft Queue</h1>
        <p className="text-muted text-sm">
          Tweets the bot drafted during off-peak hours. Approve to post at the next peak hour, edit, or reject.
        </p>
      </header>

      {(!data || data.length === 0) && (
        <div className="glass p-12 text-center text-muted text-sm">
          No drafts yet. During off-peak hours the bot will draft tweets here based on the live trends.
        </div>
      )}

      {pending.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-amber-300">Pending review · {pending.length}</h2>
          <ul className="space-y-3">
            {pending.map((d) => (
              <DraftCard
                key={d.id}
                d={d}
                isEditing={editingId === d.id}
                editText={editText}
                onStartEdit={() => {
                  setEditingId(d.id);
                  setEditText(d.thread.join("\n---\n"));
                }}
                onCancelEdit={() => setEditingId(null)}
                onChangeEditText={setEditText}
                onSaveEdit={() => handleSaveEdit(d)}
                onApprove={() => handleApprove(d)}
                onReject={() => handleReject(d)}
              />
            ))}
          </ul>
        </section>
      )}

      {approved.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold text-emerald-300">Approved — queued for posting · {approved.length}</h2>
          <ul className="space-y-3">
            {approved.map((d) => (
              <DraftCard
                key={d.id}
                d={d}
                isEditing={false}
                editText=""
                onStartEdit={() => {}}
                onCancelEdit={() => {}}
                onChangeEditText={() => {}}
                onSaveEdit={() => {}}
                onApprove={() => {}}
                onReject={() => handleReject(d)}
              />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function DraftCard({
  d,
  isEditing,
  editText,
  onStartEdit,
  onCancelEdit,
  onChangeEditText,
  onSaveEdit,
  onApprove,
  onReject,
}: {
  d: DraftItem;
  isEditing: boolean;
  editText: string;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onChangeEditText: (s: string) => void;
  onSaveEdit: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  return (
    <li className={cn("glass p-5", d.approved && "border-emerald-500/30")}>
      <div className="flex items-start justify-between gap-4 mb-3">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-[10px] uppercase tracking-widest px-2 py-1 rounded bg-lavender/15 text-lavender">
            {d.kind}
          </span>
          {d.approved && (
            <span className="text-[10px] uppercase tracking-widest px-2 py-1 rounded bg-emerald-500/15 text-emerald-300">
              approved
            </span>
          )}
          {d.edited && (
            <span className="text-[10px] uppercase tracking-widest px-2 py-1 rounded bg-amber-500/15 text-amber-300">
              edited
            </span>
          )}
          {d.title && (
            <span className="text-xs text-muted line-clamp-1">{d.title}</span>
          )}
        </div>
        <span className="text-xs text-muted shrink-0">{timeAgo(d.created_at)}</span>
      </div>

      {isEditing ? (
        <textarea
          value={editText}
          onChange={(e) => onChangeEditText(e.target.value)}
          rows={Math.max(6, editText.split("\n").length + 1)}
          className="w-full bg-black/60 border border-border rounded-lg p-3 text-sm mono mb-3"
          placeholder="Separate thread tweets with --- on their own line"
        />
      ) : (
        <div className="space-y-2 mb-3">
          {d.thread.map((t, i) => (
            <p key={i} className="text-sm whitespace-pre-wrap">{t}</p>
          ))}
        </div>
      )}

      {d.source_url && (
        <a
          href={d.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-lavender inline-flex items-center gap-1 hover:underline mb-3"
        >
          <ExternalLink size={12} /> source
        </a>
      )}

      <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-border">
        {isEditing ? (
          <>
            <button
              onClick={onSaveEdit}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-lavender text-black text-sm font-medium hover:bg-lavender/90"
            >
              <Check size={14} /> Save
            </button>
            <button
              onClick={onCancelEdit}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-white/5"
            >
              Cancel
            </button>
          </>
        ) : (
          <>
            {!d.approved && (
              <button
                onClick={onApprove}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-sm hover:bg-emerald-500/25"
              >
                <ThumbsUp size={14} /> Approve
              </button>
            )}
            {!d.approved && (
              <button
                onClick={onStartEdit}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-white/5"
              >
                <Pencil size={14} /> Edit
              </button>
            )}
            <button
              onClick={onReject}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-rose-500/40 text-rose-300 text-sm hover:bg-rose-500/10 ml-auto"
            >
              <X size={14} /> Reject
            </button>
          </>
        )}
      </div>
    </li>
  );
}
