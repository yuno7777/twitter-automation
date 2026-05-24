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
  total_likes?: number;
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
  groq_primary_model: string;
  groq_fallback_model: string;
  gemini_model: string;
  groq_primary_key_set: boolean;
  groq_fallback_key_set: boolean;
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

export function controlBot(action: "start" | "stop" | "pause" | "resume" | "reset_cycle") {
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

export interface AnalyticsResponse {
  days: number;
  daily: { date: string; tweets: number; replies: number; likes: number; follows: number }[];
  hourly: { hour: number; count: number }[];
  window_totals: { tweets: number; replies: number; likes: number; follows: number };
  busiest_day: string | null;
  top_tweets: { text: string; likes: number }[];
  totals: StatsResponse;
  cycles_run: number;
}

export function getAnalytics(days = 14) {
  return json<AnalyticsResponse>(`/api/analytics?days=${days}`);
}

export interface MemoryResponse {
  last_strategy: {
    reply_queries: string[];
    follow_queries: string[];
    like_queries: string[];
    tweet_topics: { angle: string; context: string; source_url: string }[];
    github_repos_to_mention: { name: string; why: string; url: string; stars: number; description?: string }[];
  } | null;
  last_strategy_at: string | null;
  trending_terms: string[];
  topics_seen: string[];
  repos_tracked: { name: string; ts: string }[];
  trends_to_explore_later: string[];
  recent_queries: { query: string; role: string; ts: string; candidate_count: number }[];
}

export function getMemory() {
  return json<MemoryResponse>("/api/memory");
}

export interface CreatorIntelResponse {
  fetched_at?: string;
  creators?: string[];
  top_examples?: { handle: string; text: string; likes: number; replies: number; url: string; age_minutes: number }[];
}

export function getCreatorIntel() {
  return json<CreatorIntelResponse>("/api/creator_intel");
}

export interface HealthResponse {
  status: "ok" | "warning" | "critical" | "unknown";
  follower_count: number | null;
  delta: number;
  warnings: { phrase: string; severity: string }[];
  checked_at: string | null;
  consecutive_error_cycles: number;
  adaptive_backoff_multiplier: number;
}

export function getHealth() {
  return json<HealthResponse>("/api/health");
}

export interface CookieStatusResponse {
  exists: boolean;
  age_days: number | null;
  needs_refresh: boolean;
  last_refresh: string | null;
}

export function getCookieStatus() {
  return json<CookieStatusResponse>("/api/cookie_status");
}

export interface OptimalHoursResponse {
  current_peak_hours: number[];
  recommended_peak_hours: number[];
  hour_scores: { hour: number; avg_likes: number; samples: number }[];
  sample_size: number;
}

export function getOptimalHours() {
  return json<OptimalHoursResponse>("/api/optimal_hours");
}

export interface DraftItem {
  id: string;
  kind: string;
  thread: string[];
  title?: string;
  source_url?: string;
  created_at: string;
  approved?: boolean;
  approved_at?: string;
  edited?: boolean;
}

export function getQueue() {
  return json<DraftItem[]>("/api/queue");
}

export function approveDraft(id: string) {
  return json<{ ok: boolean }>("/api/queue/approve", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export function rejectDraft(id: string) {
  return json<{ ok: boolean }>("/api/queue/reject", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export function editDraft(id: string, text: string) {
  return json<{ ok: boolean }>("/api/queue/edit", {
    method: "POST",
    body: JSON.stringify({ id, text }),
  });
}

export interface CriticEntry {
  ts: string;
  role: string;
  score: number;
  issues: string[];
  attempt: number;
  accepted: boolean;
}

export function getCriticLog() {
  return json<CriticEntry[]>("/api/critic_log");
}

export interface QuoteHistoryItem {
  quote_text: string;
  original_tweet_url: string;
  original_tweet_text?: string;
  original_likes?: number;
  posted_at: string;
}

export interface FollowUpHistoryItem {
  your_tweet: string;
  their_reply: string;
  your_followup: string;
  thread_url: string;
  posted_at: string;
}

export function getQuoteHistory() {
  return json<QuoteHistoryItem[]>("/api/history/quotes");
}

export function getFollowUpHistory() {
  return json<FollowUpHistoryItem[]>("/api/history/follow_ups");
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
