const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type BotStatus = "running" | "paused" | "stopped";

export interface StatusResponse {
  status: BotStatus;
  current_action: string;
  next_cycle_at: string | null;
  last_run: string | null;
}

export interface StatsResponse {
  total_tweets: number;
  total_replies: number;
  total_follows: number;
  llm_calls_today: number;
  cycles_run: number;
  status?: BotStatus;
  next_cycle_at?: string | null;
  last_run?: string | null;
}

export interface TweetHistoryItem {
  text: string;
  posted_at: string;
  news_title?: string;
  news_link?: string;
}

export interface ReplyHistoryItem {
  reply_text: string;
  original_tweet_url: string;
  original_tweet_text?: string;
  posted_at: string;
}

export interface FollowHistoryItem {
  username: string;
  followed_at: string;
  follower_count?: string;
}

export interface BotSettings {
  llm_provider: string;
  cycle_interval_hours: number;
  max_posts_per_cycle: number;
  max_replies_per_cycle: number;
  max_follows_per_cycle: number;
  headless: string;
  dry_run: string;
  proxy_configured: boolean;
  tweet_prompt: string;
  reply_prompt: string;
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export const fetcher = <T,>(path: string) => json<T>(path);

export function getBotStatus() {
  return json<StatusResponse>("/api/status");
}

export function controlBot(action: "start" | "stop" | "pause" | "resume") {
  return json<{ ok: boolean; status: BotStatus }>("/api/control", {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export function getStats() {
  return json<StatsResponse>("/api/stats");
}

export function getTweetHistory() {
  return json<TweetHistoryItem[]>("/api/history/tweets");
}

export function getReplyHistory() {
  return json<ReplyHistoryItem[]>("/api/history/replies");
}

export function getFollowHistory() {
  return json<FollowHistoryItem[]>("/api/history/follows");
}

export function getLogs(lines = 200) {
  return json<{ lines: string[] }>(`/api/logs?lines=${lines}`);
}

export function getSettings() {
  return json<BotSettings>("/api/settings");
}

export function updateSettings(settings: Partial<BotSettings>) {
  return json<{ ok: boolean; updated: string[] }>("/api/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  });
}

export const logsStreamUrl = `${API_BASE}/api/logs/stream`;
