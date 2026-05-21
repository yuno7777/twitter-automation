"use client";

import { useEffect, useRef, useState } from "react";
import { logsStreamUrl } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Eraser, ArrowDownToLine } from "lucide-react";

function classifyLine(line: string): "info" | "warn" | "error" {
  if (/\bERROR\b/.test(line)) return "error";
  if (/\bWARN(?:ING)?\b/.test(line)) return "warn";
  return "info";
}

export default function LogsPage() {
  const [lines, setLines] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const es = new EventSource(logsStreamUrl);
    es.onmessage = (e) => {
      setLines((prev) => {
        const next = [...prev, e.data];
        return next.length > 2000 ? next.slice(-2000) : next;
      });
    };
    es.onerror = () => {
      // Browser will auto-reconnect
    };
    return () => es.close();
  }, []);

  useEffect(() => {
    if (autoScroll && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Live Logs</h1>
          <p className="text-muted text-sm">Streaming from x_bot.log via SSE.</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setAutoScroll((v) => !v)}
            className={cn(
              "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs",
              autoScroll ? "border-lavender/40 text-lavender" : "border-border text-muted"
            )}
          >
            <ArrowDownToLine size={14} /> Auto-scroll
          </button>
          <button
            onClick={() => setLines([])}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border text-xs hover:bg-white/5"
          >
            <Eraser size={14} /> Clear
          </button>
        </div>
      </header>

      <div className="text-xs text-muted">Showing last {lines.length} lines</div>

      <div
        ref={boxRef}
        className="glass mono text-xs leading-relaxed h-[70vh] overflow-y-auto p-4 bg-black/40"
      >
        {lines.length === 0 && (
          <div className="text-muted">Waiting for log stream…</div>
        )}
        {lines.map((ln, i) => {
          const cls = classifyLine(ln);
          return (
            <div
              key={i}
              className={cn(
                "whitespace-pre-wrap break-words",
                cls === "info" && "text-white/90",
                cls === "warn" && "text-amber-300",
                cls === "error" && "text-rose-400"
              )}
            >
              {ln}
            </div>
          );
        })}
      </div>
    </div>
  );
}
