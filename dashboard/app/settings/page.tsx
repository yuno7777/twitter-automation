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
        groq_primary_model: draft.groq_primary_model,
        groq_fallback_model: draft.groq_fallback_model,
        gemini_model: draft.gemini_model,
        cycle_interval_hours: draft.cycle_interval_hours,
        max_posts_per_cycle: draft.max_posts_per_cycle,
        max_replies_per_cycle: draft.max_replies_per_cycle,
        max_follows_per_cycle: draft.max_follows_per_cycle,
        tweet_prompt: draft.tweet_prompt,
        reply_prompt: draft.reply_prompt,
      });
      toast.success("Settings saved — restart bot for changes to take effect");
      mutate();
    } catch (e: any) {
      toast.error(e.message || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
  ];
  const GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
  ];

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

      <section className="glass p-6 space-y-5">
        <div>
          <h2 className="font-semibold text-lg">LLM Cascade</h2>
          <p className="text-xs text-muted mt-1">
            3-tier fallback: primary fails → tier 2 takes over → Gemini as last resort.
            Each Groq tier can use its own API key for separate rate-limit budgets.
          </p>
        </div>

        <ModelField
          label="Tier 1 — Groq primary"
          help="Best reasoning + JSON. Used for strategy synthesis, critic, reply analyzer."
          value={draft.groq_primary_model}
          onChange={(v) => set("groq_primary_model", v)}
          options={GROQ_MODELS}
          keySet={draft.groq_primary_key_set}
          keyEnv="GROQ_PRIMARY_API_KEY"
        />

        <ModelField
          label="Tier 2 — Groq fallback"
          help="Triggers on Tier 1 rate limit or error. Different model + (recommended) different API key."
          value={draft.groq_fallback_model}
          onChange={(v) => set("groq_fallback_model", v)}
          options={GROQ_MODELS}
          keySet={draft.groq_fallback_key_set}
          keyEnv="GROQ_FALLBACK_API_KEY"
        />

        <ModelField
          label="Tier 3 — Gemini (last resort)"
          help="Different provider entirely. Only fires if both Groq tiers fail."
          value={draft.gemini_model}
          onChange={(v) => set("gemini_model", v)}
          options={GEMINI_MODELS}
          keySet={true}
          keyEnv="GEMINI_API_KEY"
        />

        <div className="text-xs text-muted pt-2 border-t border-border">
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

function ModelField({
  label,
  help,
  value,
  onChange,
  options,
  keySet,
  keyEnv,
}: {
  label: string;
  help: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  keySet: boolean;
  keyEnv: string;
}) {
  // Allow free-text via combobox pattern — datalist of common options + raw input.
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3 flex-wrap">
        <label className="text-sm font-medium text-white">{label}</label>
        <span className={
          "text-[10px] uppercase tracking-widest px-2 py-0.5 rounded " +
          (keySet
            ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
            : "bg-rose-500/15 text-rose-300 border border-rose-500/30")
        }>
          {keySet ? "API key set" : `${keyEnv} missing`}
        </span>
      </div>
      <p className="text-xs text-muted">{help}</p>
      <input
        list={`models-${keyEnv}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-black/60 border border-border rounded-lg px-3 py-2 text-sm mono"
        placeholder="model id"
      />
      <datalist id={`models-${keyEnv}`}>
        {options.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>
    </div>
  );
}
