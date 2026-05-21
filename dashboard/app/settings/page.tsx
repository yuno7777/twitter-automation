"use client";

import useSWR from "swr";
import { useEffect, useState } from "react";
import { fetcher, BotSettings, updateSettings } from "@/lib/api";
import { Save } from "lucide-react";
import { toast } from "sonner";

export default function SettingsPage() {
  const { data, mutate } = useSWR<BotSettings>("/api/settings", fetcher);
  const [draft, setDraft] = useState<BotSettings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data && !draft) setDraft(data);
  }, [data, draft]);

  if (!draft) {
    return <div className="text-muted text-sm">Loading settings…</div>;
  }

  function set<K extends keyof BotSettings>(k: K, v: BotSettings[K]) {
    setDraft((d) => (d ? { ...d, [k]: v } : d));
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    try {
      await updateSettings({
        llm_provider: draft.llm_provider,
        cycle_interval_hours: draft.cycle_interval_hours,
        max_posts_per_cycle: draft.max_posts_per_cycle,
        max_replies_per_cycle: draft.max_replies_per_cycle,
        max_follows_per_cycle: draft.max_follows_per_cycle,
        tweet_prompt: draft.tweet_prompt,
        reply_prompt: draft.reply_prompt,
      });
      toast.success("Settings saved");
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <header>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted text-sm">
          Changes are persisted to <code className="mono">.env</code> and the prompt files.
          Restart the bot for env changes to take effect.
        </p>
      </header>

      <section className="glass p-6 space-y-4">
        <h2 className="font-semibold text-lg">Cycle Limits</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <NumberField label="Cycle interval (h)" value={draft.cycle_interval_hours} onChange={(v) => set("cycle_interval_hours", v)} />
          <NumberField label="Max posts" value={draft.max_posts_per_cycle} onChange={(v) => set("max_posts_per_cycle", v)} />
          <NumberField label="Max replies" value={draft.max_replies_per_cycle} onChange={(v) => set("max_replies_per_cycle", v)} />
          <NumberField label="Max follows" value={draft.max_follows_per_cycle} onChange={(v) => set("max_follows_per_cycle", v)} />
        </div>
      </section>

      <section className="glass p-6 space-y-4">
        <h2 className="font-semibold text-lg">LLM Provider</h2>
        <div className="flex items-center gap-3">
          <label className="text-sm text-muted">Primary provider</label>
          <select
            value={draft.llm_provider}
            onChange={(e) => set("llm_provider", e.target.value)}
            className="bg-black/60 border border-border rounded-lg px-3 py-2 text-sm"
          >
            <option value="groq">Groq</option>
            <option value="gemini">Gemini</option>
          </select>
        </div>
        <div className="text-xs text-muted">
          Proxy: {draft.proxy_configured ? "configured" : "not configured"} • Headless: {draft.headless} • Dry-run: {draft.dry_run}
        </div>
      </section>

      <section className="glass p-6 space-y-3">
        <h2 className="font-semibold text-lg">Tweet Prompt</h2>
        <textarea
          value={draft.tweet_prompt}
          onChange={(e) => set("tweet_prompt", e.target.value)}
          rows={14}
          className="w-full bg-black/60 border border-border rounded-lg p-3 text-sm mono"
        />
      </section>

      <section className="glass p-6 space-y-3">
        <h2 className="font-semibold text-lg">Reply Prompt</h2>
        <textarea
          value={draft.reply_prompt}
          onChange={(e) => set("reply_prompt", e.target.value)}
          rows={10}
          className="w-full bg-black/60 border border-border rounded-lg p-3 text-sm mono"
        />
      </section>

      <div className="flex justify-end">
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-lavender text-black font-medium hover:bg-lavender/90 disabled:opacity-50 transition"
        >
          <Save size={16} /> {saving ? "Saving…" : "Save Settings"}
        </button>
      </div>
    </div>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-muted">{label}</span>
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value || "0", 10))}
        className="bg-black/60 border border-border rounded-lg px-3 py-2 text-sm mono"
      />
    </label>
  );
}
