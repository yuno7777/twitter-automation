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
    action: Literal["start", "stop", "pause", "resume"]


class SettingsBody(BaseModel):
    llm_provider: str | None = None
    cycle_interval_hours: int | None = None
    max_posts_per_cycle: int | None = None
    max_replies_per_cycle: int | None = None
    max_follows_per_cycle: int | None = None
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
    write_state(s)
    return {"ok": True, "status": s["status"]}


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
