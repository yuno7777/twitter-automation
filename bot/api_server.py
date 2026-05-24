"""
FastAPI bridge between the X automation bot and the Next.js dashboard.

Run:
    uvicorn api_server:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv, set_key
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

BOT_DIR = Path(__file__).resolve().parent
ROOT_DIR = BOT_DIR.parent
STATE_PATH = BOT_DIR / "bot_state.json"
LOG_PATH = BOT_DIR / "x_bot.log"
PROMPTS_DIR = BOT_DIR / "prompts"
ENV_PATH = ROOT_DIR / ".env"

load_dotenv(ENV_PATH)

app = FastAPI(title="X Bot Control API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "status": "stopped",
            "current_action": "Bot has never run",
            "stats": {
                "total_tweets": 0, "total_replies": 0, "total_follows": 0,
                "llm_calls_today": 0, "cycles_run": 0,
            },
            "tweet_history": [], "reply_history": [], "follow_history": [],
            "next_cycle_at": None, "last_run": None,
        }
    with STATE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.replace(STATE_PATH)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ControlBody(BaseModel):
    action: Literal["start", "stop", "pause", "resume", "reset_cycle"]


class SettingsBody(BaseModel):
    llm_provider: str | None = None
    cycle_interval_hours: int | None = None
    max_posts_per_cycle: int | None = None
    max_replies_per_cycle: int | None = None
    max_follows_per_cycle: int | None = None
    groq_primary_model: str | None = None
    groq_fallback_model: str | None = None
    gemini_model: str | None = None
    tweet_prompt: str | None = None
    reply_prompt: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status() -> dict[str, Any]:
    s = read_state()
    return {
        "status": s.get("status", "stopped"),
        "current_action": s.get("current_action", "idle"),
        "next_cycle_at": s.get("next_cycle_at"),
        "last_run": s.get("last_run"),
    }


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return read_state()


@app.post("/api/control")
def control(body: ControlBody) -> dict[str, Any]:
    s = read_state()
    if body.action in ("start", "resume"):
        s["status"] = "running"
    elif body.action == "pause":
        s["status"] = "paused"
    elif body.action == "stop":
        s["status"] = "stopped"
    elif body.action == "reset_cycle":
        # Flag is consumed by the bot's long_wait / inter-cycle sleep
        s["status"] = "running"
        s["force_new_cycle"] = True
    write_state(s)
    return {"ok": True, "status": s["status"], "force_new_cycle": s.get("force_new_cycle", False)}


@app.get("/api/logs")
def get_logs(lines: int = Query(200, ge=1, le=5000)) -> dict[str, Any]:
    if not LOG_PATH.exists():
        return {"lines": []}
    with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    return {"lines": [ln.rstrip("\n") for ln in all_lines[-lines:]]}


@app.get("/api/logs/stream")
async def stream_logs():
    """SSE endpoint — tails x_bot.log line by line."""
    async def event_stream():
        # Send last 50 lines on connect, then tail
        last_pos = 0
        if LOG_PATH.exists():
            with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                for ln in lines[-50:]:
                    yield f"data: {ln.rstrip()}\n\n"
                f.seek(0, 2)
                last_pos = f.tell()

        while True:
            try:
                if LOG_PATH.exists():
                    with LOG_PATH.open("r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new = f.read()
                        last_pos = f.tell()
                    if new:
                        for ln in new.splitlines():
                            if ln.strip():
                                yield f"data: {ln}\n\n"
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"data: [stream error] {e}\n\n"
                await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history/tweets")
def history_tweets() -> list[dict[str, Any]]:
    return read_state().get("tweet_history", [])


@app.get("/api/history/replies")
def history_replies() -> list[dict[str, Any]]:
    return read_state().get("reply_history", [])


@app.get("/api/history/follows")
def history_follows() -> list[dict[str, Any]]:
    return read_state().get("follow_history", [])


@app.get("/api/history/likes")
def history_likes() -> list[dict[str, Any]]:
    return read_state().get("like_history", [])


@app.get("/api/history/quotes")
def history_quotes() -> list[dict[str, Any]]:
    return read_state().get("quote_history", [])


@app.get("/api/history/follow_ups")
def history_follow_ups() -> list[dict[str, Any]]:
    return read_state().get("follow_up_history", [])


@app.get("/api/critic_log")
def critic_log() -> list[dict[str, Any]]:
    return read_state().get("critic_log", [])


# --- Draft queue endpoints ---

class DraftActionBody(BaseModel):
    id: str
    text: str | None = None  # for edit


@app.get("/api/queue")
def get_queue() -> list[dict[str, Any]]:
    return read_state().get("draft_queue", [])


@app.post("/api/queue/approve")
def approve_draft(body: DraftActionBody) -> dict[str, Any]:
    s = read_state()
    found = False
    for d in s.get("draft_queue", []):
        if d.get("id") == body.id:
            d["approved"] = True
            d["approved_at"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Draft not found")
    write_state(s)
    return {"ok": True}


@app.post("/api/queue/reject")
def reject_draft(body: DraftActionBody) -> dict[str, Any]:
    s = read_state()
    before = len(s.get("draft_queue", []))
    s["draft_queue"] = [d for d in s.get("draft_queue", []) if d.get("id") != body.id]
    if len(s["draft_queue"]) == before:
        raise HTTPException(status_code=404, detail="Draft not found")
    write_state(s)
    return {"ok": True}


@app.post("/api/queue/edit")
def edit_draft(body: DraftActionBody) -> dict[str, Any]:
    if body.text is None:
        raise HTTPException(status_code=400, detail="text required")
    s = read_state()
    for d in s.get("draft_queue", []):
        if d.get("id") == body.id:
            # Split edited text on --- to keep thread format
            parts = [p.strip() for p in body.text.split("\n---\n") if p.strip()]
            if not parts:
                parts = [body.text.strip()]
            d["thread"] = parts
            d["edited"] = True
            write_state(s)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Draft not found")


@app.get("/api/creator_intel")
def get_creator_intel() -> dict[str, Any]:
    return read_state().get("creator_intel", {})


COOKIES_PATH = BOT_DIR / "cookies.json"


@app.get("/api/cookie_status")
def cookie_status() -> dict[str, Any]:
    """Cookie age + refresh recommendation. Triggers banner in dashboard."""
    if not COOKIES_PATH.exists():
        return {"exists": False, "age_days": None, "needs_refresh": True, "last_refresh": None}
    mtime = datetime.fromtimestamp(COOKIES_PATH.stat().st_mtime, tz=timezone.utc)
    age_days = (datetime.now(timezone.utc) - mtime).days
    return {
        "exists": True,
        "age_days": age_days,
        "needs_refresh": age_days >= 30,
        "last_refresh": mtime.isoformat(),
    }


@app.get("/api/health")
def get_health() -> dict[str, Any]:
    """Account health snapshot — feeds dashboard banner."""
    s = read_state()
    h = s.get("account_health", {}) or {}
    return {
        "status": h.get("status", "unknown"),
        "follower_count": h.get("follower_count"),
        "delta": h.get("delta", 0),
        "warnings": h.get("warnings", []),
        "checked_at": h.get("checked_at"),
        "consecutive_error_cycles": s.get("consecutive_error_cycles", 0),
        "adaptive_backoff_multiplier": min(8, 2 ** max(0, int(s.get("consecutive_error_cycles", 0)) - 1)) if s.get("consecutive_error_cycles", 0) else 1,
    }


@app.get("/api/optimal_hours")
def optimal_hours() -> dict[str, Any]:
    """Compute optimal posting hours from tweet history + engagement.
    Uses the bot's own top_tweets snapshot (which has likes) cross-referenced with tweet_history (which has posted_at).
    """
    s = read_state()
    tweet_history = s.get("tweet_history", [])
    top_tweets = s.get("top_tweets", [])
    top_lookup = {(t.get("text") or "").strip()[:80]: t.get("likes", 0) for t in top_tweets}

    # Bucket by local hour, average likes
    from collections import defaultdict
    hour_likes: dict[int, list[int]] = defaultdict(list)
    for t in tweet_history:
        ts = t.get("posted_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        except Exception:
            continue
        text_key = (t.get("text") or "").strip()[:80]
        likes = top_lookup.get(text_key, 0)
        hour_likes[dt.hour].append(likes)

    # Score per hour: avg likes (penalize hours with <2 samples)
    scored = []
    for hour, likes_list in hour_likes.items():
        if not likes_list:
            continue
        avg = sum(likes_list) / len(likes_list)
        scored.append({"hour": hour, "avg_likes": round(avg, 2), "samples": len(likes_list)})
    scored.sort(key=lambda x: x["avg_likes"], reverse=True)
    recommended = [s["hour"] for s in scored[:7]] if scored else []

    current = os.getenv("PEAK_HOURS", "").strip()
    return {
        "current_peak_hours": [int(h) for h in current.split(",") if h.strip().isdigit()] if current else [],
        "recommended_peak_hours": sorted(recommended),
        "hour_scores": scored,
        "sample_size": len(tweet_history),
    }


@app.get("/api/memory")
def get_memory() -> dict[str, Any]:
    """Trend-discovery memory — last strategy, topics seen, repos tracked, queued trends."""
    m = read_state().get("search_memory", {})
    last = m.get("last_strategy") or {}
    return {
        "last_strategy": m.get("last_strategy"),
        "last_strategy_at": m.get("last_strategy_at"),
        "trending_terms": last.get("_trending_terms") or last.get("trending_terms") or [],
        "topics_seen": (m.get("topics_seen") or [])[-50:],
        "repos_tracked": (m.get("github_repos_tracked") or [])[-30:],
        "trends_to_explore_later": (m.get("trends_to_explore_later") or [])[-25:],
        "recent_queries": (m.get("queries_run") or [])[-40:],
    }


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


@app.get("/api/analytics")
def analytics(days: int = Query(14, ge=1, le=90)) -> dict[str, Any]:
    """Aggregate history into daily series + hourly heatmap + top tweets."""
    s = read_state()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Build day buckets (oldest -> newest)
    day_keys: list[str] = []
    for i in range(days - 1, -1, -1):
        day_keys.append((now - timedelta(days=i)).strftime("%Y-%m-%d"))

    daily: dict[str, dict[str, int]] = {
        k: {"date": k, "tweets": 0, "replies": 0, "likes": 0, "follows": 0}
        for k in day_keys
    }
    hourly = [0] * 24  # 24-hour activity heatmap (any action)

    def bucket(items: list[dict[str, Any]], ts_key: str, action: str) -> None:
        for it in items:
            dt = _parse_iso(it.get(ts_key))
            if not dt:
                continue
            if dt < cutoff:
                continue
            local = dt.astimezone()  # server local; matches PEAK_HOURS
            key = local.strftime("%Y-%m-%d")
            if key in daily:
                daily[key][action] += 1
            hourly[local.hour] += 1

    bucket(s.get("tweet_history", []), "posted_at", "tweets")
    bucket(s.get("reply_history", []), "posted_at", "replies")
    bucket(s.get("like_history", []), "liked_at", "likes")
    bucket(s.get("follow_history", []), "followed_at", "follows")

    daily_series = [daily[k] for k in day_keys]

    # Totals over the window
    window_totals = {
        "tweets": sum(d["tweets"] for d in daily_series),
        "replies": sum(d["replies"] for d in daily_series),
        "likes": sum(d["likes"] for d in daily_series),
        "follows": sum(d["follows"] for d in daily_series),
    }
    busiest_day = max(daily_series, key=lambda d: d["tweets"] + d["replies"] + d["likes"] + d["follows"], default=None)

    return {
        "days": days,
        "daily": daily_series,
        "hourly": [{"hour": h, "count": c} for h, c in enumerate(hourly)],
        "window_totals": window_totals,
        "busiest_day": busiest_day["date"] if busiest_day else None,
        "top_tweets": s.get("top_tweets", [])[:5],
        "totals": s.get("stats", {}),
        "cycles_run": s.get("stats", {}).get("cycles_run", 0),
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    s = read_state()
    return {
        **s.get("stats", {}),
        "status": s.get("status"),
        "next_cycle_at": s.get("next_cycle_at"),
        "last_run": s.get("last_run"),
    }


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    tweet_prompt = ""
    reply_prompt = ""
    try:
        tweet_prompt = (PROMPTS_DIR / "tweet_prompt.txt").read_text(encoding="utf-8")
        reply_prompt = (PROMPTS_DIR / "reply_prompt.txt").read_text(encoding="utf-8")
    except Exception:
        pass
    return {
        "llm_provider": os.getenv("LLM_PROVIDER", "groq"),
        "groq_primary_model": os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b"),
        "groq_fallback_model": os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile"),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "groq_primary_key_set": bool(os.getenv("GROQ_PRIMARY_API_KEY", "").strip() or os.getenv("GROQ_API_KEY", "").strip()),
        "groq_fallback_key_set": bool(os.getenv("GROQ_FALLBACK_API_KEY", "").strip() or os.getenv("GROQ_API_KEY", "").strip()),
        "cycle_interval_hours": int(os.getenv("CYCLE_INTERVAL_HOURS", "5")),
        "max_posts_per_cycle": int(os.getenv("MAX_POSTS_PER_CYCLE", "3")),
        "max_replies_per_cycle": int(os.getenv("MAX_REPLIES_PER_CYCLE", "1")),
        "max_follows_per_cycle": int(os.getenv("MAX_FOLLOWS_PER_CYCLE", "2")),
        "headless": os.getenv("HEADLESS", "true"),
        "dry_run": os.getenv("DRY_RUN", "false"),
        "proxy_configured": bool(os.getenv("PROXY_URL", "").strip()),
        "tweet_prompt": tweet_prompt,
        "reply_prompt": reply_prompt,
    }


@app.post("/api/settings")
def update_settings(body: SettingsBody) -> dict[str, Any]:
    # Persist env vars
    env_updates: dict[str, str] = {}
    if body.llm_provider is not None:
        env_updates["LLM_PROVIDER"] = body.llm_provider
    if body.cycle_interval_hours is not None:
        env_updates["CYCLE_INTERVAL_HOURS"] = str(body.cycle_interval_hours)
    if body.max_posts_per_cycle is not None:
        env_updates["MAX_POSTS_PER_CYCLE"] = str(body.max_posts_per_cycle)
    if body.max_replies_per_cycle is not None:
        env_updates["MAX_REPLIES_PER_CYCLE"] = str(body.max_replies_per_cycle)
    if body.max_follows_per_cycle is not None:
        env_updates["MAX_FOLLOWS_PER_CYCLE"] = str(body.max_follows_per_cycle)
    if body.groq_primary_model is not None:
        env_updates["GROQ_PRIMARY_MODEL"] = body.groq_primary_model
    if body.groq_fallback_model is not None:
        env_updates["GROQ_FALLBACK_MODEL"] = body.groq_fallback_model
    if body.gemini_model is not None:
        env_updates["GEMINI_MODEL"] = body.gemini_model

    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")

    for k, v in env_updates.items():
        try:
            set_key(str(ENV_PATH), k, v)
            os.environ[k] = v
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write env: {e}")

    if body.tweet_prompt is not None:
        (PROMPTS_DIR / "tweet_prompt.txt").write_text(body.tweet_prompt, encoding="utf-8")
    if body.reply_prompt is not None:
        (PROMPTS_DIR / "reply_prompt.txt").write_text(body.reply_prompt, encoding="utf-8")

    return {"ok": True, "updated": list(env_updates.keys())}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "x-bot-api", "status": "ok"}
