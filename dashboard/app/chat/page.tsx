"use client";

import useSWR from "swr";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ChatMessage,
  NudgeItem,
  ProposedAction,
  AiActionLogItem,
  clearChat,
  confirmAction,
  dismissNudge,
  fetcher,
  getActionsLog,
  getChatHistory,
  sendChat,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import {
  AlertTriangle,
  Check,
  Info,
  Send,
  Sparkles,
  Trash2,
  X,
  Wrench,
} from "lucide-react";

const SUGGESTIONS = [
  "How's the bot doing today?",
  "Why are my replies low?",
  "Lean more into quotes, less replying",
  "What's my best-performing tweet?",
  "Add @swyx to the VIP list",
];

export default function ChatPage() {
  const { data: history, mutate: mutateHistory } = useSWR<ChatMessage[]>(
    "/api/chat/history",
    fetcher,
    { refreshInterval: 0 }
  );
  const { data: nudges, mutate: mutateNudges } = useSWR<NudgeItem[]>(
    "/api/nudges",
    fetcher,
    { refreshInterval: 15000 }
  );
  const { data: actionsLog, mutate: mutateLog } = useSWR<AiActionLogItem[]>(
    "/api/chat/actions_log",
    fetcher,
    { refreshInterval: 0 }
  );

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());
  const scrollRef = useRef<HTMLDivElement>(null);

  const messages = history ?? [];

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, sending]);

  async function send(text: string) {
    const msg = text.trim();
    if (!msg || sending) return;
    setSending(true);
    setInput("");
    // optimistic user bubble
    mutateHistory(
      [...messages, { role: "user", content: msg, ts: new Date().toISOString() }],
      { revalidate: false }
    );
    try {
      await sendChat(msg);
      await mutateHistory();
    } catch (e: any) {
      toast.error(e.message || "Chat failed");
    } finally {
      setSending(false);
    }
  }

  async function onApply(a: ProposedAction) {
    try {
      const res = await confirmAction(a.tool, a.args);
      if (res.ok) {
        toast.success(res.message);
        setAppliedIds((s) => new Set(s).add(a.id));
        mutateLog();
      } else {
        toast.error(res.message);
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to apply");
    }
  }

  async function onClear() {
    await clearChat();
    mutateHistory([], { revalidate: false });
    setAppliedIds(new Set());
  }

  async function onDismissNudge(id: string) {
    await dismissNudge(id);
    mutateNudges();
  }

  return (
    <div className="max-w-4xl mx-auto h-[calc(100vh-3rem)] flex flex-col gap-4">
      <header className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
            <Sparkles size={26} className="text-lavender" /> Co-Pilot
          </h1>
          <p className="text-muted text-sm">
            Talk to your bot. It can see everything and propose changes you approve.
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={onClear}
            className="text-xs text-muted hover:text-rose-300 flex items-center gap-1 transition"
          >
            <Trash2 size={13} /> Clear
          </button>
        )}
      </header>

      {/* Proactive nudges */}
      {nudges && nudges.length > 0 && (
        <div className="space-y-2 shrink-0">
          {nudges.map((n) => (
            <NudgeCard key={n.id} nudge={n} onDismiss={() => onDismissNudge(n.id)} onAsk={() => send(n.text)} />
          ))}
        </div>
      )}

      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-lavender to-lavender-deep flex items-center justify-center lavender-glow">
              <Sparkles size={26} className="text-black" />
            </div>
            <p className="text-muted text-sm max-w-sm">
              Ask about performance, request changes in plain English, or let it
              flag problems. Every change needs your approval.
            </p>
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="glass px-3 py-1.5 text-xs text-muted hover:text-white hover:border-lavender/40 transition"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            msg={m}
            appliedIds={appliedIds}
            onApply={onApply}
          />
        ))}

        {sending && (
          <div className="flex items-center gap-2 text-muted text-sm">
            <span className="w-2 h-2 rounded-full bg-lavender animate-pulse" />
            <span className="w-2 h-2 rounded-full bg-lavender animate-pulse [animation-delay:150ms]" />
            <span className="w-2 h-2 rounded-full bg-lavender animate-pulse [animation-delay:300ms]" />
            <span className="ml-1">thinking…</span>
          </div>
        )}
      </div>

      {/* Action audit log (collapsible-ish summary) */}
      {actionsLog && actionsLog.length > 0 && (
        <details className="glass p-3 text-xs shrink-0">
          <summary className="cursor-pointer text-muted hover:text-white">
            Applied changes ({actionsLog.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {actionsLog.slice(0, 8).map((a, i) => (
              <li key={i} className="flex items-center gap-2 text-muted">
                <Wrench size={11} className="text-lavender shrink-0" />
                <span className="flex-1">{a.message}</span>
                <span className="mono">{timeAgo(a.applied_at)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {/* Composer */}
      <div className="shrink-0 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(input);
            }
          }}
          rows={1}
          placeholder="Ask anything, or tell it what to change…"
          className="flex-1 resize-none glass px-4 py-3 text-sm outline-none focus:border-lavender/50 max-h-32"
        />
        <button
          onClick={() => send(input)}
          disabled={sending || !input.trim()}
          className="h-12 w-12 rounded-xl bg-lavender text-black flex items-center justify-center disabled:opacity-40 hover:bg-lavender-deep transition"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}

function NudgeCard({
  nudge,
  onDismiss,
  onAsk,
}: {
  nudge: NudgeItem;
  onDismiss: () => void;
  onAsk: () => void;
}) {
  const styles = {
    info: "border-sky-500/40 bg-sky-500/10",
    warning: "border-amber-500/40 bg-amber-500/10",
    critical: "border-rose-500/50 bg-rose-500/10",
  }[nudge.severity];
  const Icon = nudge.severity === "info" ? Info : AlertTriangle;
  const iconColor =
    nudge.severity === "info"
      ? "text-sky-300"
      : nudge.severity === "warning"
      ? "text-amber-300"
      : "text-rose-300";
  return (
    <div className={cn("glass p-3 flex items-start gap-3", styles)}>
      <Icon size={16} className={cn("mt-0.5 shrink-0", iconColor)} />
      <p className="flex-1 text-sm">{nudge.text}</p>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={onAsk}
          className="text-xs px-2 py-1 rounded-md bg-lavender/15 text-lavender hover:bg-lavender/25 transition"
        >
          Discuss
        </button>
        <button onClick={onDismiss} className="text-muted hover:text-white">
          <X size={14} />
        </button>
      </div>
    </div>
  );
}

function MessageBubble({
  msg,
  appliedIds,
  onApply,
}: {
  msg: ChatMessage;
  appliedIds: Set<string>;
  onApply: (a: ProposedAction) => void;
}) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] space-y-2", isUser && "items-end")}>
        <div
          className={cn(
            "px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap",
            isUser
              ? "bg-lavender text-black rounded-br-sm"
              : "glass rounded-bl-sm"
          )}
        >
          {msg.content || <span className="text-muted italic">…</span>}
        </div>

        {/* Proposed action cards */}
        {!isUser &&
          msg.proposed_actions &&
          msg.proposed_actions.map((a) => (
            <ActionCard
              key={a.id}
              action={a}
              applied={appliedIds.has(a.id)}
              onApply={() => onApply(a)}
            />
          ))}
      </div>
    </div>
  );
}

function ActionCard({
  action,
  applied,
  onApply,
}: {
  action: ProposedAction;
  applied: boolean;
  onApply: () => void;
}) {
  const argStr = Object.entries(action.args)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return (
    <div className="glass p-3 border-lavender/30">
      <div className="flex items-center gap-2 text-xs">
        <Wrench size={13} className="text-lavender" />
        <span className="mono text-lavender">{action.tool}</span>
        <span className="mono text-muted">{argStr}</span>
      </div>
      {action.reason && <p className="text-xs text-muted mt-1.5">{action.reason}</p>}
      {!action.valid && (
        <p className="text-xs text-rose-300 mt-1.5 flex items-center gap-1">
          <AlertTriangle size={11} /> {action.validation_error}
        </p>
      )}
      <div className="mt-2.5 flex items-center gap-2">
        {applied ? (
          <span className="text-xs text-emerald-300 flex items-center gap-1">
            <Check size={13} /> Applied
          </span>
        ) : (
          <button
            onClick={onApply}
            disabled={!action.valid}
            className="text-xs px-3 py-1.5 rounded-md bg-lavender text-black font-medium disabled:opacity-40 hover:bg-lavender-deep transition"
          >
            Apply
          </button>
        )}
      </div>
    </div>
  );
}
