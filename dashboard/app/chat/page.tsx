"use client";

import useSWR from "swr";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  ChatAttachment,
  ChatMessage,
  ChatSessionMeta,
  NudgeItem,
  ProposedAction,
  confirmAction,
  createSession,
  deleteSession,
  dismissNudge,
  fetcher,
  getSession,
  listSessions,
  sendChat,
} from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import {
  AlertTriangle,
  Brain,
  Check,
  ChevronDown,
  FileText,
  Image as ImageIcon,
  Info,
  MessageSquarePlus,
  Paperclip,
  Send,
  Sparkles,
  Trash2,
  X,
  Wrench,
} from "lucide-react";

const MAX_FILE_BYTES = 6 * 1024 * 1024;
const MAX_FILES = 4;
const ACCEPT =
  "image/png,image/jpeg,image/webp,image/gif,application/pdf,text/plain,text/markdown,text/csv";

const SUGGESTIONS = [
  "How's the bot doing today?",
  "Why are my replies low?",
  "Lean more into quotes, less replying",
  "What's my best-performing tweet?",
];

interface PendingFile {
  name: string;
  mime: string;
  size: number;
  data_base64: string;
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",", 2)[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function ChatPage() {
  const { data: sessions, mutate: mutateSessions } = useSWR<ChatSessionMeta[]>(
    "/api/chat/sessions",
    fetcher,
    { refreshInterval: 0 }
  );
  const { data: nudges, mutate: mutateNudges } = useSWR<NudgeItem[]>(
    "/api/nudges",
    fetcher,
    { refreshInterval: 15000 }
  );

  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [appliedIds, setAppliedIds] = useState<Set<string>>(new Set());
  const [files, setFiles] = useState<PendingFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bootstrapped = useRef(false);

  // Bootstrap: pick newest session or create one
  useEffect(() => {
    if (bootstrapped.current || !sessions) return;
    bootstrapped.current = true;
    (async () => {
      if (sessions.length > 0) {
        await selectSession(sessions[0].id);
      } else {
        const s = await createSession();
        await mutateSessions();
        setActiveId(s.id);
        setMessages([]);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  const selectSession = useCallback(async (id: string) => {
    setActiveId(id);
    setAppliedIds(new Set());
    try {
      const full = await getSession(id);
      setMessages(full.messages || []);
    } catch {
      setMessages([]);
    }
  }, []);

  async function onNewChat() {
    const s = await createSession();
    await mutateSessions();
    setActiveId(s.id);
    setMessages([]);
    setAppliedIds(new Set());
    setInput("");
    setFiles([]);
  }

  async function onDeleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await deleteSession(id);
    const fresh = await mutateSessions();
    if (id === activeId) {
      if (fresh && fresh.length > 0) await selectSession(fresh[0].id);
      else await onNewChat();
    }
  }

  async function onPickFiles(list: FileList | null) {
    if (!list) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (next.length >= MAX_FILES) {
        toast.error(`Max ${MAX_FILES} files`);
        break;
      }
      if (f.size > MAX_FILE_BYTES) {
        toast.error(`${f.name} is over 6MB`);
        continue;
      }
      try {
        const data = await readFileAsBase64(f);
        next.push({ name: f.name, mime: f.type || "application/octet-stream", size: f.size, data_base64: data });
      } catch {
        toast.error(`Couldn't read ${f.name}`);
      }
    }
    setFiles(next);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function send(text: string) {
    const msg = text.trim();
    if ((!msg && files.length === 0) || sending || !activeId) return;
    setSending(true);
    setInput("");
    const attached = files;
    setFiles([]);
    const marker = attached.length ? `\n[attached: ${attached.map((f) => f.name).join(", ")}]` : "";
    setMessages((prev) => [
      ...prev,
      { role: "user", content: (msg + marker).trim(), ts: new Date().toISOString() },
    ]);
    try {
      const payload: ChatAttachment[] = attached.map((f) => ({
        name: f.name,
        mime: f.mime,
        data_base64: f.data_base64,
      }));
      const reply = await sendChat(activeId, msg || "(see attached)", payload);
      setMessages((prev) => [...prev, reply]);
      mutateSessions(); // title may have changed
    } catch (e: any) {
      toast.error(e.message || "Chat failed");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong sending that.", ts: new Date().toISOString() },
      ]);
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
      } else {
        toast.error(res.message);
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to apply");
    }
  }

  return (
    <div className="h-full flex gap-4">
      {/* Session list */}
      <aside className="hidden md:flex w-60 shrink-0 flex-col gap-2">
        <button
          onClick={onNewChat}
          className="glass px-3 py-2.5 flex items-center gap-2 text-sm hover:border-lavender/40 transition shrink-0"
        >
          <MessageSquarePlus size={16} className="text-lavender" />
          New chat
        </button>
        <div className="flex-1 overflow-y-auto min-h-0 space-y-1 pr-1">
          {(sessions || []).map((s) => (
            <div
              key={s.id}
              onClick={() => selectSession(s.id)}
              className={cn(
                "group px-3 py-2 rounded-lg text-sm cursor-pointer transition flex items-center gap-2",
                s.id === activeId
                  ? "bg-lavender/15 text-lavender border border-lavender/30"
                  : "text-muted hover:text-white hover:bg-white/5 border border-transparent"
              )}
            >
              <span className="flex-1 truncate">{s.title || "Chat"}</span>
              <button
                onClick={(e) => onDeleteSession(s.id, e)}
                className="opacity-0 group-hover:opacity-100 text-muted hover:text-rose-300 transition"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      {/* Conversation */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between shrink-0 mb-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Sparkles size={22} className="text-lavender" /> Co-Pilot
            </h1>
            <p className="text-muted text-xs">
              Sees the whole bot · remembers across chats · proposes changes you approve
            </p>
          </div>
          <button
            onClick={onNewChat}
            className="md:hidden glass px-2.5 py-2 text-xs flex items-center gap-1"
          >
            <MessageSquarePlus size={14} /> New
          </button>
        </header>

        {/* Nudges */}
        {nudges && nudges.length > 0 && (
          <div className="space-y-2 shrink-0 mb-3">
            {nudges.map((n) => (
              <NudgeCard
                key={n.id}
                nudge={n}
                onDismiss={async () => {
                  await dismissNudge(n.id);
                  mutateNudges();
                }}
                onAsk={() => send(n.text)}
              />
            ))}
          </div>
        )}

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1">
          {messages.length === 0 && !sending && (
            <div className="h-full flex flex-col items-center justify-center text-center gap-4">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-lavender to-lavender-deep flex items-center justify-center lavender-glow">
                <Sparkles size={26} className="text-black" />
              </div>
              <p className="text-muted text-sm max-w-sm">
                Ask about performance, attach an analytics screenshot, or request
                changes in plain English. Every change needs your approval.
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
            <MessageBubble key={i} msg={m} appliedIds={appliedIds} onApply={onApply} />
          ))}

          {sending && <ThinkingIndicator />}
        </div>

        {/* Pending attachments */}
        {files.length > 0 && (
          <div className="shrink-0 flex flex-wrap gap-2 mt-3">
            {files.map((f, i) => (
              <div key={i} className="glass px-2.5 py-1.5 flex items-center gap-2 text-xs">
                {f.mime.startsWith("image/") ? (
                  <ImageIcon size={13} className="text-lavender" />
                ) : (
                  <FileText size={13} className="text-lavender" />
                )}
                <span className="max-w-[160px] truncate">{f.name}</span>
                <span className="text-muted mono">{(f.size / 1024).toFixed(0)}KB</span>
                <button
                  onClick={() => setFiles(files.filter((_, idx) => idx !== i))}
                  className="text-muted hover:text-rose-300"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Composer */}
        <div className="shrink-0 flex items-end gap-2 mt-3">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT}
            multiple
            hidden
            onChange={(e) => onPickFiles(e.target.files)}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            title="Attach images, PDFs, or text files"
            className="h-12 w-12 rounded-xl glass flex items-center justify-center text-muted hover:text-lavender hover:border-lavender/40 transition shrink-0"
          >
            <Paperclip size={18} />
          </button>
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
            placeholder="Ask anything, attach a screenshot, or tell it what to change…"
            className="flex-1 resize-none glass px-4 py-3 text-sm outline-none focus:border-lavender/50 max-h-32"
          />
          <button
            onClick={() => send(input)}
            disabled={sending || (!input.trim() && files.length === 0)}
            className="h-12 w-12 rounded-xl bg-lavender text-black flex items-center justify-center disabled:opacity-40 hover:bg-lavender-deep transition shrink-0"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

function ThinkingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="glass rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-2 text-muted text-sm">
        <Brain size={14} className="text-lavender animate-pulse" />
        <span className="w-1.5 h-1.5 rounded-full bg-lavender animate-pulse" />
        <span className="w-1.5 h-1.5 rounded-full bg-lavender animate-pulse [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-lavender animate-pulse [animation-delay:300ms]" />
        <span className="ml-1">thinking…</span>
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
      <div className="max-w-[85%] space-y-2">
        {!isUser && msg.thinking ? <ThinkingBlock text={msg.thinking} /> : null}
        <div
          className={cn(
            "px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap",
            isUser ? "bg-lavender text-black rounded-br-sm" : "glass rounded-bl-sm"
          )}
        >
          {msg.content || <span className="text-muted italic">…</span>}
        </div>
        {!isUser &&
          msg.proposed_actions &&
          msg.proposed_actions.map((a) => (
            <ActionCard key={a.id} action={a} applied={appliedIds.has(a.id)} onApply={() => onApply(a)} />
          ))}
      </div>
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 text-muted hover:text-lavender transition"
      >
        <Brain size={12} />
        <span>Thought process</span>
        <ChevronDown size={12} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-1.5 pl-3 border-l-2 border-lavender/30 text-muted leading-relaxed whitespace-pre-wrap">
          {text}
        </div>
      )}
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
      <div className="flex items-center gap-2 text-xs flex-wrap">
        <Wrench size={13} className="text-lavender" />
        <span className="mono text-lavender">{action.tool}</span>
        <span className="mono text-muted break-all">{argStr}</span>
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
