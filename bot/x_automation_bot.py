"""
X / Twitter Automation Bot
==========================

Autonomous growth + content bot for X (Twitter).
- Fetches AI/tech news from RSS every ~5 hours
- Generates beautiful tweets via Groq (with Gemini fallback)
- Posts, replies, and follows via Playwright with manual stealth patches
- Long human-like delays between every action
- Persists state across runs in bot_state.json

Run:
    1. Copy .env.example to .env and fill in API keys.
    2. First run (headed): HEADLESS=false python x_automation_bot.py login
       Manually log in to X in the browser; the bot saves cookies.json.
    3. Subsequent runs: python x_automation_bot.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import quote_plus

import feedparser
from dotenv import load_dotenv
from playwright.async_api import BrowserContext, Page, async_playwright

import intelligence
import creator_intel

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

BOT_DIR = Path(__file__).resolve().parent
STATE_PATH = BOT_DIR / "bot_state.json"
COOKIES_PATH = BOT_DIR / "cookies.json"
LOG_PATH = BOT_DIR / "x_bot.log"
SCREENSHOT_DIR = BOT_DIR / "debug_screenshots"
PROMPTS_DIR = BOT_DIR / "prompts"

SCREENSHOT_DIR.mkdir(exist_ok=True)

# Logging — to console + file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("x_bot")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

CYCLE_INTERVAL_HOURS = 2
MAX_POSTS_PER_CYCLE = int(os.getenv("MAX_POSTS_PER_CYCLE", "1"))
MAX_REPLIES_PER_CYCLE = int(os.getenv("MAX_REPLIES_PER_CYCLE", "5"))
MAX_FOLLOWS_PER_CYCLE = int(os.getenv("MAX_FOLLOWS_PER_CYCLE", "2"))
MAX_LIKES_PER_CYCLE = int(os.getenv("MAX_LIKES_PER_CYCLE", "10"))
MAX_QUOTES_PER_CYCLE = int(os.getenv("MAX_QUOTES_PER_CYCLE", "1"))
MAX_FOLLOW_UPS_PER_CYCLE = int(os.getenv("MAX_FOLLOW_UPS_PER_CYCLE", "2"))

NICHE = os.getenv("NICHE", "AI, automation, and tech").strip()
X_HANDLE = os.getenv("X_HANDLE", "").strip().lstrip("@")
PEAK_HOURS_RAW = os.getenv("PEAK_HOURS", "").strip()
PEAK_HOURS = [int(h) for h in PEAK_HOURS_RAW.split(",") if h.strip().isdigit()] if PEAK_HOURS_RAW else []

# Curated creators in your niche — bot scrapes their top tweets each cycle for style reference.
CREATORS_TO_STUDY = [
    h.strip().lstrip("@") for h in os.getenv("CREATORS_TO_STUDY", "").split(",")
    if h.strip()
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://arstechnica.com/feed/",
    "https://hnrss.org/frontpage",
    "https://artificialintelligence-news.com/feed/",
]

REPLY_SEARCH_QUERIES = [
    "AI agents",
    "Claude AI",
    "Cursor AI",
    "LLM",
    "n8n",
    "AI tools",
    "indie hacker",
    "shipping AI",
    "vibe coding",
    "AI startup",
    "RAG",
    "AI workflow",
]

FOLLOW_SEARCH_QUERIES = [
    "AI founder",
    "automation builder",
    "SaaS founder",
    "machine learning engineer",
    "AI tools",
]

# Centralized selectors — update here if X changes its UI
SELECTORS = {
    "compose_tweet_btn": '[data-testid="SideNav_NewTweet_Button"]',
    # Scope to the modal dialog — the home feed has a separate inline textarea
    # with the same data-testid that steals first-match but not focus.
    "tweet_textarea": '[role="dialog"] [data-testid="tweetTextarea_0"]',
    "tweet_textarea_unscoped": '[data-testid="tweetTextarea_0"]',  # fallback only
    "tweet_submit_btn": '[role="dialog"] [data-testid="tweetButtonInline"]',
    "tweet_submit_btn_modal": '[role="dialog"] [data-testid="tweetButton"]',
    "tweet_card": '[data-testid="tweet"]',
    "tweet_text": '[data-testid="tweetText"]',
    "reply_btn": '[data-testid="reply"]',
    "like_btn": '[data-testid="like"]',
    "user_cell": '[data-testid="UserCell"]',
    "ad_marker": '[data-testid="placementTracking"]',
    "thread_add_btn": '[data-testid="addButton"]',
    "retweet_btn": '[data-testid="retweet"]',
    "quote_menu_item": '[data-testid="unretweetConfirm"]',  # placeholder; we use text match in code
}


def in_peak_hour() -> bool:
    """True if PEAK_HOURS is unset, or current local hour is in PEAK_HOURS."""
    if not PEAK_HOURS:
        return True
    return datetime.now().hour in PEAK_HOURS

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

DEFAULT_STATE: dict[str, Any] = {
    "status": "running",        # running | paused | stopped
    "current_action": "idle",
    "next_cycle_at": None,
    "processed_links": [],
    "replied_tweet_ids": [],
    "liked_tweet_ids": [],
    "followed_usernames": [],
    "tweet_history": [],
    "reply_history": [],
    "follow_history": [],
    "like_history": [],
    "quote_history": [],
    "follow_up_history": [],
    "top_tweets": [],            # best-performing recent own tweets
    "bottom_tweets": [],         # worst-performing recent own tweets (negative reference)
    "responded_thread_ids": [],  # threads where we already did a follow-up
    "draft_queue": [],           # off-hours drafts pending your approval
    "critic_log": [],            # last 50 critic decisions for the dashboard
    # Trend-discovery memory — grows over time, drives smarter searches
    "search_memory": {
        "queries_run": [],                # [{query, ts, candidate_count, role}]
        "topics_seen": [],                # de-duped list of topics already covered
        "github_repos_tracked": [],       # repos already tweeted/mentioned
        "trends_to_explore_later": [],    # queued for future cycles
        "last_strategy": None,            # most recent strategy dict
        "last_strategy_at": None,
    },
    "stats": {
        "total_tweets": 0,
        "total_replies": 0,
        "total_follows": 0,
        "total_likes": 0,
        "llm_calls_today": 0,
        "cycles_run": 0,
    },
    "last_run": None,
}


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        save_state(DEFAULT_STATE)
        return json.loads(json.dumps(DEFAULT_STATE))
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Backfill missing keys
        for k, v in DEFAULT_STATE.items():
            data.setdefault(k, v)
        data["stats"] = {**DEFAULT_STATE["stats"], **data.get("stats", {})}
        return data
    except Exception as e:
        logger.error(f"Failed to load state, resetting: {e}")
        save_state(DEFAULT_STATE)
        return json.loads(json.dumps(DEFAULT_STATE))


def save_state(state: dict[str, Any]) -> None:
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.replace(STATE_PATH)


def set_action(state: dict[str, Any], action: str) -> None:
    state["current_action"] = action
    save_state(state)
    logger.info(f"[ACTION] {action}")


def check_control_flag() -> str:
    """Read just the status field from state — cheap polling for pause/stop."""
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f).get("status", "running")
    except Exception:
        return "running"


def check_force_new_cycle() -> bool:
    """True if the dashboard requested an immediate cycle restart."""
    try:
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return bool(json.load(f).get("force_new_cycle", False))
    except Exception:
        return False


def consume_force_new_cycle(state: dict[str, Any]) -> None:
    """Clear the flag after we've acknowledged it."""
    state["force_new_cycle"] = False
    save_state(state)


async def respect_control(state: dict[str, Any]) -> bool:
    """Returns True if the bot should continue, False if it should exit the cycle."""
    flag = check_control_flag()
    state["status"] = flag
    if flag == "paused":
        logger.info("Bot is paused — sleeping 30s and re-checking.")
        while check_control_flag() == "paused":
            await asyncio.sleep(30)
        logger.info("Resumed.")
    if flag == "stopped":
        logger.info("Bot status is 'stopped' — exiting cycle.")
        return False
    return True


# ---------------------------------------------------------------------------
# LLM wrapper — 3-tier cascade
# ---------------------------------------------------------------------------
#   1. Groq · openai/gpt-oss-120b           (primary — best reasoning + JSON)
#   2. Groq · llama-3.3-70b-versatile       (Groq fallback — same provider, different model)
#   3. Google · gemini-2.5-flash            (last-resort fallback — different provider)

GROQ_PRIMARY_MODEL  = os.getenv("GROQ_PRIMARY_MODEL",  "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL",        "gemini-2.5-flash")

# Per-tier API keys — lets you split rate-limit budgets across two Groq accounts.
# Falls back to the single GROQ_API_KEY if a tier-specific key isn't set.
GROQ_PRIMARY_API_KEY  = os.getenv("GROQ_PRIMARY_API_KEY",  "").strip() or GROQ_API_KEY
GROQ_FALLBACK_API_KEY = os.getenv("GROQ_FALLBACK_API_KEY", "").strip() or GROQ_API_KEY

_groq_clients: dict[str, Any] = {}  # cache by API key
_gemini_configured = False


def _get_groq(api_key: str | None):
    """Get (or build) a Groq client for the given API key. Caches per-key."""
    if not api_key:
        return None
    if api_key not in _groq_clients:
        from groq import Groq
        _groq_clients[api_key] = Groq(api_key=api_key)
    return _groq_clients[api_key]


def _configure_gemini():
    global _gemini_configured
    if not _gemini_configured and GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_configured = True


async def _try_groq(model: str, api_key: str | None, user_prompt: str, system_prompt: str) -> str | None:
    client = _get_groq(api_key)
    if client is None:
        return None
    resp = await asyncio.to_thread(
        client.chat.completions.create,
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.85,
        max_tokens=600,
    )
    return resp.choices[0].message.content.strip()


async def _try_gemini(user_prompt: str, system_prompt: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    _configure_gemini()
    import google.generativeai as genai
    model = genai.GenerativeModel(GEMINI_MODEL)
    result = await asyncio.to_thread(
        model.generate_content, f"{system_prompt}\n\n{user_prompt}"
    )
    return (result.text or "").strip()


async def call_llm(user_prompt: str, system_prompt: str, state: dict[str, Any]) -> str | None:
    """3-tier cascade: GPT-OSS-120B → Llama-3.3-70B → Gemini-2.5-Flash."""
    state["stats"]["llm_calls_today"] = state["stats"].get("llm_calls_today", 0) + 1

    attempts: list[tuple[str, str]] = []  # (label, error preview)

    # Tier 1 — Groq primary (GPT-OSS-120B with primary API key)
    try:
        out = await _try_groq(GROQ_PRIMARY_MODEL, GROQ_PRIMARY_API_KEY, user_prompt, system_prompt)
        if out:
            return out
    except Exception as e:
        attempts.append((f"groq/{GROQ_PRIMARY_MODEL}", str(e)[:120]))
        logger.warning(f"LLM primary '{GROQ_PRIMARY_MODEL}' failed: {e}")
        await asyncio.sleep(3)

    # Tier 2 — Groq fallback (Llama 3.3 with fallback API key — own rate budget)
    try:
        out = await _try_groq(GROQ_FALLBACK_MODEL, GROQ_FALLBACK_API_KEY, user_prompt, system_prompt)
        if out:
            logger.info(f"LLM fallback to '{GROQ_FALLBACK_MODEL}' succeeded.")
            return out
    except Exception as e:
        attempts.append((f"groq/{GROQ_FALLBACK_MODEL}", str(e)[:120]))
        logger.warning(f"LLM fallback '{GROQ_FALLBACK_MODEL}' failed: {e}")
        await asyncio.sleep(3)

    # Tier 3 — Gemini (different provider, last resort)
    try:
        out = await _try_gemini(user_prompt, system_prompt)
        if out:
            logger.info(f"LLM last-resort fallback to '{GEMINI_MODEL}' succeeded.")
            return out
    except Exception as e:
        attempts.append((f"gemini/{GEMINI_MODEL}", str(e)[:120]))
        logger.warning(f"LLM last-resort '{GEMINI_MODEL}' failed: {e}")

    logger.error(f"All LLM tiers failed. Attempts: {attempts}")
    return None


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _dedupe_keep_order(xs: list[str], cap: int = 200) -> list[str]:
    seen = set()
    out: list[str] = []
    for x in xs:
        k = x.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    return out[-cap:]


def merge_memory(state: dict[str, Any], strategy: dict[str, Any]) -> None:
    """Fold a fresh strategy's memory_updates into long-term state."""
    mem = state.setdefault("search_memory", {})
    saved = {k: v for k, v in strategy.items() if not k.startswith("_")}
    # Preserve deterministically extracted trending terms (LLM-independent)
    saved["trending_terms"] = strategy.get("_trending_terms", [])
    mem["last_strategy"] = saved
    mem["last_strategy_at"] = datetime.now(timezone.utc).isoformat()

    mu = strategy.get("memory_updates", {}) or {}
    if mu.get("topics_seen_add"):
        mem["topics_seen"] = _dedupe_keep_order(
            (mem.get("topics_seen") or []) + list(mu["topics_seen_add"])
        )
    if mu.get("trends_to_explore_later"):
        mem["trends_to_explore_later"] = _dedupe_keep_order(
            (mem.get("trends_to_explore_later") or []) + list(mu["trends_to_explore_later"]),
            cap=50,
        )
    save_state(state)


def record_query_run(state: dict[str, Any], query: str, role: str, count: int) -> None:
    mem = state.setdefault("search_memory", {})
    mem.setdefault("queries_run", []).append({
        "query": query,
        "role": role,
        "ts": datetime.now(timezone.utc).isoformat(),
        "candidate_count": count,
    })
    mem["queries_run"] = mem["queries_run"][-200:]
    save_state(state)


def record_repo_tracked(state: dict[str, Any], repo_name: str) -> None:
    mem = state.setdefault("search_memory", {})
    tracked = mem.setdefault("github_repos_tracked", [])
    if repo_name and repo_name not in [r.get("name") for r in tracked]:
        tracked.append({"name": repo_name, "ts": datetime.now(timezone.utc).isoformat()})
        mem["github_repos_tracked"] = tracked[-100:]
        save_state(state)


def load_style_notes() -> str:
    try:
        return (PROMPTS_DIR / "style_notes.txt").read_text(encoding="utf-8").strip()
    except Exception:
        return "(none provided)"


def format_top_tweets(state: dict[str, Any], n: int = 3) -> str:
    top = state.get("top_tweets") or []
    bottom = state.get("bottom_tweets") or []
    if not top and not bottom:
        return "(no engagement data yet)"
    out: list[str] = []
    if top:
        out.append("TOP PERFORMERS — write more like these:")
        for t in top[:n]:
            likes = t.get("likes", 0)
            text = (t.get("text") or "").replace("\n", " ")[:200]
            out.append(f"  + ({likes} likes) {text}")
    if bottom:
        out.append("UNDERPERFORMERS — avoid this style:")
        for t in bottom[:n]:
            likes = t.get("likes", 0)
            text = (t.get("text") or "").replace("\n", " ")[:200]
            out.append(f"  - ({likes} likes) {text}")
    return "\n".join(out)


def log_critic(state: dict[str, Any], role: str, score: int, issues: list[str], attempt: int, accepted: bool) -> None:
    """Keep a rolling log of critic decisions for dashboard visibility."""
    state.setdefault("critic_log", []).insert(0, {
        "ts": datetime.now(timezone.utc).isoformat(),
        "role": role,
        "score": score,
        "issues": issues[:5],
        "attempt": attempt,
        "accepted": accepted,
    })
    state["critic_log"] = state["critic_log"][:50]


def split_thread(text: str) -> list[str]:
    """Split LLM output on lines containing only '---' into a list of tweets."""
    parts = re.split(r"^\s*-{3,}\s*$", text, flags=re.MULTILINE)
    tweets = [strip_markdown(p).strip().strip('"').strip("'") for p in parts]
    tweets = [t for t in tweets if t]
    # Truncate each
    out = []
    for t in tweets[:3]:
        if len(t) > 280:
            t = t[:277].rstrip() + "..."
        out.append(t)
    return out


# ---------------------------------------------------------------------------
# News ingestion
# ---------------------------------------------------------------------------

@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    source: str
    published: datetime


def fetch_news(state: dict[str, Any]) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=18)
    seen_urls: set[str] = set()
    items: list[NewsItem] = []

    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            source = feed.feed.get("title", url)
            for entry in feed.entries[:25]:
                link = entry.get("link", "")
                if not link or link in seen_urls:
                    continue
                if link in state["processed_links"]:
                    continue

                # Parse publish date
                published_dt: datetime | None = None
                for key in ("published_parsed", "updated_parsed"):
                    val = entry.get(key)
                    if val:
                        published_dt = datetime(*val[:6], tzinfo=timezone.utc)
                        break
                if not published_dt or published_dt < cutoff:
                    continue

                seen_urls.add(link)
                items.append(NewsItem(
                    title=entry.get("title", "").strip(),
                    summary=re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:600].strip(),
                    link=link,
                    source=source,
                    published=published_dt,
                ))
        except Exception as e:
            logger.warning(f"Feed failed ({url}): {e}")

    items.sort(key=lambda x: x.published, reverse=True)
    logger.info(f"Fetched {len(items)} fresh news items across {len(RSS_FEEDS)} feeds")
    return items


# ---------------------------------------------------------------------------
# Stealth patches
# ---------------------------------------------------------------------------

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
window.chrome = { runtime: {} };
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);
"""


async def apply_stealth_patches(context: BrowserContext) -> None:
    await context.add_init_script(STEALTH_JS)


# ---------------------------------------------------------------------------
# Human-like helpers
# ---------------------------------------------------------------------------

async def jitter(min_s: float = 0.5, max_s: float = 3.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


def _adaptive_multiplier(state: dict[str, Any]) -> float:
    """Multiplier for cooldowns based on consecutive error cycles.
    1 -> 1x · 2 -> 2x · 3 -> 4x · 4+ -> 8x (capped)."""
    err = int(state.get("consecutive_error_cycles", 0) or 0)
    if err <= 0:
        return 1.0
    return float(min(8, 2 ** (err - 1)))


async def long_wait(min_min: float, max_min: float, state: dict[str, Any], reason: str) -> None:
    mult = _adaptive_multiplier(state)
    minutes = random.uniform(min_min, max_min) * mult
    seconds = minutes * 60
    label = f"{reason} (~{int(minutes)} min{f', backoff x{mult:.0f}' if mult > 1 else ''})"
    set_action(state, label)
    logger.info(f"Sleeping {minutes:.1f} min — {reason}{f' (backoff x{mult:.0f})' if mult > 1 else ''}")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check_control_flag() == "stopped":
            logger.info("Stop flag detected during long wait — aborting.")
            return
        if check_force_new_cycle():
            logger.info(f"Force-new-cycle requested during '{reason}' — breaking out.")
            return
        await asyncio.sleep(min(5, end - time.monotonic()))


async def human_type(page: Page, selector: str, text: str) -> None:
    await page.click(selector, timeout=10000)
    await jitter(0.3, 0.8)
    await page.type(selector, text, delay=random.randint(60, 140))


async def random_mouse_move(page: Page) -> None:
    try:
        await page.mouse.move(
            random.randint(100, 900),
            random.randint(100, 600),
            steps=random.randint(5, 15),
        )
    except Exception:
        pass


async def safe_action(coro, page: Page, label: str) -> Any:
    """Wrap a Playwright coroutine; on failure, take a screenshot and return None."""
    try:
        return await coro
    except Exception as e:
        ts = int(time.time())
        path = SCREENSHOT_DIR / f"fail_{label}_{ts}.png"
        try:
            await page.screenshot(path=str(path), full_page=False)
        except Exception:
            pass
        logger.warning(f"Selector/action failed [{label}]: {e}. Screenshot: {path}")
        return None


# ---------------------------------------------------------------------------
# Browser launch
# ---------------------------------------------------------------------------

async def launch_browser(playwright, headless: bool = True) -> tuple[Any, BrowserContext]:
    """Launch real Chrome with persistent profile — the only reliable path against X's bot detection."""
    proxy = {"server": PROXY_URL} if PROXY_URL else None
    if proxy:
        logger.info(f"Proxy active: {PROXY_URL.split('@')[-1]}")
    else:
        logger.info("Proxy active: no")

    profile_dir = BOT_DIR / "chrome_profile"
    profile_dir.mkdir(exist_ok=True)

    viewport_w = random.choice([1280, 1360, 1440])
    viewport_h = random.choice([800, 850, 900])

    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "channel": "chrome",
        "headless": headless,
        "viewport": {"width": viewport_w, "height": viewport_h},
        "locale": "en-US",
        "timezone_id": "America/Los_Angeles",
        "args": [
            "--disable-blink-features=AutomationControlled",
        ],
    }
    if proxy:
        launch_kwargs["proxy"] = proxy

    context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
    await apply_stealth_patches(context)
    # Persistent context has no separate Browser handle; return context twice for API parity.
    return context, context


# ---------------------------------------------------------------------------
# Login flow
# ---------------------------------------------------------------------------

async def login_flow() -> None:
    """Headed login — uses your real Chrome (channel='chrome') with a persistent profile.

    X aggressively blocks Playwright's bundled Chromium during login. Using your
    installed Chrome with a dedicated user-data-dir bypasses that.
    """
    profile_dir = BOT_DIR / "chrome_profile"
    profile_dir.mkdir(exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",  # use installed Chrome, not bundled Chromium
            headless=False,
            viewport={"width": 1360, "height": 850},
            locale="en-US",
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )
        await apply_stealth_patches(context)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://x.com/login", wait_until="domcontentloaded")
        logger.info("=" * 60)
        logger.info("Please log in manually in the Chromium browser window.")
        logger.info("Auto-saving cookies once you reach the home feed.")
        logger.info("=" * 60)

        # Poll for login completion (URL contains /home or compose button visible).
        # Allow up to 15 minutes for the user to complete login.
        deadline = time.monotonic() + 15 * 60
        saved = False
        while time.monotonic() < deadline:
            try:
                current_url = page.url
                if "/home" in current_url or "/i/flow" not in current_url and "/login" not in current_url and "/i/oauth" not in current_url:
                    # Double-check the home compose button is visible
                    try:
                        await page.wait_for_selector(SELECTORS["compose_tweet_btn"], timeout=3000)
                        await context.storage_state(path=str(COOKIES_PATH))
                        logger.info(f"Login detected. Cookies saved to {COOKIES_PATH}")
                        saved = True
                        break
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(3)

        if not saved:
            logger.error("Login not detected within 15 minutes. Closing browser without saving cookies.")
        await asyncio.sleep(2)
        await context.close()


# ---------------------------------------------------------------------------
# Text post-processing
# ---------------------------------------------------------------------------

def strip_markdown(text: str) -> str:
    """Strip markdown formatting that X doesn't render."""
    # Bold/italic: **text** __text__ *text* _text_ — keep inner text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", text)
    # Inline code: `text`
    text = re.sub(r"`+([^`]+)`+", r"\1", text)
    # Markdown headers at line start
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Markdown links [label](url) -> label (X auto-linkifies bare URLs)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tweet generation
# ---------------------------------------------------------------------------

CRITIC_THRESHOLD = 7
CRITIC_MAX_ATTEMPTS = 3


async def _gate_with_critic(
    generator: Callable[[], Awaitable[Any]],
    serializer: Callable[[Any], str],
    role: str,
    state: dict[str, Any],
) -> Any:
    """Run a generator, critique the output, regenerate up to MAX_ATTEMPTS if score < threshold."""
    best: Any = None
    best_score = -1
    for attempt in range(1, CRITIC_MAX_ATTEMPTS + 1):
        candidate = await generator()
        if not candidate:
            continue
        text = serializer(candidate)
        if not text or len(text.strip()) < 10:
            continue
        verdict = await intelligence.critique_text(
            text, role, NICHE, load_style_notes(),
            lambda u, s: call_llm(u, s, state),
        )
        score = verdict["score"]
        issues = verdict.get("issues", [])
        accepted = score >= CRITIC_THRESHOLD
        log_critic(state, role, score, issues, attempt, accepted)
        logger.info(f"Critic[{role} attempt {attempt}]: score={score} issues={issues[:3]}")
        save_state(state)
        if accepted:
            return candidate
        # Track best-so-far in case all attempts fail
        if score > best_score:
            best_score, best = score, candidate
    # Fall back to best of N rather than skip — better imperfect post than nothing
    if best is not None:
        logger.info(f"Critic[{role}]: no attempt cleared threshold, posting best (score={best_score})")
    return best


async def generate_thread(item: NewsItem, state: dict[str, Any]) -> list[str]:
    """Returns 1-3 tweets as a list. Empty list on failure."""
    template = load_prompt("tweet_prompt")
    mode_name, mode_instructions = creator_intel.pick_style_mode()
    user_prompt = template.format(
        niche=NICHE,
        style_notes=load_style_notes(),
        creator_examples=creator_intel.format_creator_examples(state),
        top_tweets=format_top_tweets(state),
        style_mode_name=mode_name,
        style_mode_instructions=mode_instructions,
        title=item.title,
        summary=item.summary,
        source=item.source,
        link=item.link,
    )
    text = await call_llm(user_prompt, "You write sharp, opinionated X posts that grow accounts.", state)
    if not text:
        return []
    return split_thread(text)


async def generate_trend_thread(topic: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Turn a strategy tweet_topic (from real GitHub/HN signal) into a 1-3 tweet thread."""
    template = load_prompt("trend_tweet_prompt")
    mode_name, mode_instructions = creator_intel.pick_style_mode()
    user_prompt = template.format(
        niche=NICHE,
        style_notes=load_style_notes(),
        creator_examples=creator_intel.format_creator_examples(state),
        top_tweets=format_top_tweets(state),
        style_mode_name=mode_name,
        style_mode_instructions=mode_instructions,
        angle=topic.get("angle", ""),
        context=topic.get("context", ""),
        source_url=topic.get("source_url", ""),
    )
    text = await call_llm(user_prompt, "You write sharp builder-focused X posts.", state)
    if not text:
        return []
    return split_thread(text)


async def generate_reply(
    tweet_text: str,
    state: dict[str, Any],
    classification: str = "genuine",
    sentiment: str = "neutral",
    reply_style: str = "offer_specific_insight",
) -> str | None:
    template = load_prompt("reply_prompt")
    user_prompt = template.format(
        niche=NICHE,
        style_notes=load_style_notes(),
        tweet_text=tweet_text,
        classification=classification,
        sentiment=sentiment,
        reply_style=reply_style,
    )
    text = await call_llm(user_prompt, "You write replies that add real signal.", state)
    if not text:
        return None
    text = strip_markdown(text).strip('"').strip("'")
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return text


async def generate_quote(tweet_text: str, state: dict[str, Any]) -> str | None:
    template = load_prompt("quote_prompt")
    user_prompt = template.format(
        niche=NICHE,
        style_notes=load_style_notes(),
        top_tweets=format_top_tweets(state),
        tweet_text=tweet_text,
    )
    text = await call_llm(user_prompt, "You write sharp quote-tweets that piggyback on viral posts.", state)
    if not text:
        return None
    text = strip_markdown(text).strip('"').strip("'")
    if len(text) > 260:
        text = text[:257].rstrip() + "..."
    return text


async def generate_follow_up(your_tweet: str, their_reply: str, sentiment: str, state: dict[str, Any]) -> str | None:
    template = load_prompt("follow_up_prompt")
    user_prompt = template.format(
        niche=NICHE,
        style_notes=load_style_notes(),
        your_tweet=your_tweet,
        their_reply=their_reply,
        sentiment=sentiment,
    )
    text = await call_llm(user_prompt, "You continue conversations as a thoughtful builder.", state)
    if not text:
        return None
    text = strip_markdown(text).strip('"').strip("'")
    # Allow the LLM to skip
    if text.strip().upper() in ("SKIP", '"SKIP"'):
        return None
    if len(text) > 220:
        text = text[:217].rstrip() + "..."
    return text


# ---------------------------------------------------------------------------
# Posting
# ---------------------------------------------------------------------------

async def selector_health_check(page: Page) -> bool:
    """Verify compose tweet button is visible — indicates UI is intact."""
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 4)
        await page.wait_for_selector(SELECTORS["compose_tweet_btn"], timeout=15000)
        return True
    except Exception as e:
        logger.warning(f"Selector health check failed — UI may have changed: {e}")
        await safe_action(page.screenshot(path=str(SCREENSHOT_DIR / f"health_check_{int(time.time())}.png")), page, "health")
        return False


async def post_tweet(page: Page, text: str) -> bool:
    return await post_thread(page, [text])


_OG_IMAGE_RE = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?(?:property|name)\s*=\s*["\'](?:og:image|twitter:image)["\'][^>]*?content\s*=\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_REV = re.compile(
    r'<meta\s+(?:[^>]*?\s+)?content\s*=\s*["\']([^"\']+)["\'][^>]*?(?:property|name)\s*=\s*["\'](?:og:image|twitter:image)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_CACHE: dict[str, Path | None] = {}  # url -> downloaded path (or None if no image)


async def fetch_og_image(url: str) -> Path | None:
    """Fetch <meta property=og:image> from a URL, download to temp, return Path.
    Best-effort. Returns None if no image, network error, or unsupported format."""
    if not url or not url.startswith("http"):
        return None
    if url in _OG_IMAGE_CACHE:
        return _OG_IMAGE_CACHE[url]

    import httpx
    out_path: Path | None = None
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(url)
            if r.status_code != 200:
                _OG_IMAGE_CACHE[url] = None
                return None
            html = r.text[:200_000]  # cap so we don't parse huge pages
            m = _OG_IMAGE_RE.search(html) or _OG_IMAGE_RE_REV.search(html)
            if not m:
                _OG_IMAGE_CACHE[url] = None
                return None
            img_url = m.group(1).strip()
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                from urllib.parse import urlparse, urlunparse
                p = urlparse(url)
                img_url = urlunparse((p.scheme, p.netloc, img_url, "", "", ""))
            # Skip unsupported / tiny placeholder images
            if any(x in img_url.lower() for x in (".svg", "1x1.", "spacer", "pixel.gif")):
                _OG_IMAGE_CACHE[url] = None
                return None

            ir = await client.get(img_url)
            if ir.status_code != 200 or len(ir.content) < 2048:
                _OG_IMAGE_CACHE[url] = None
                return None

            ext = ".jpg"
            ctype = (ir.headers.get("content-type") or "").lower()
            if "png" in ctype: ext = ".png"
            elif "webp" in ctype: ext = ".webp"
            elif "gif" in ctype: ext = ".gif"
            elif ".png" in img_url.lower(): ext = ".png"
            elif ".webp" in img_url.lower(): ext = ".webp"

            out_dir = BOT_DIR / "og_images"
            out_dir.mkdir(exist_ok=True)
            out_path = out_dir / f"og_{int(time.time()*1000)}{ext}"
            out_path.write_bytes(ir.content)
            logger.info(f"OG image fetched for tweet: {out_path.name} ({len(ir.content)//1024}KB)")
    except Exception as e:
        logger.warning(f"OG image fetch failed for {url}: {e}")
        out_path = None

    if out_path is None:
        logger.info(f"OG image: no usable image found at {url[:80]}")
    _OG_IMAGE_CACHE[url] = out_path
    return out_path


async def post_thread(page: Page, tweets: list[str], image_path: Path | None = None) -> bool:
    """Post 1-N tweets as a single thread using X's native + button."""
    if not tweets:
        return False
    if DRY_RUN:
        for i, t in enumerate(tweets):
            logger.info(f"[DRY_RUN] Would post thread tweet {i+1}/{len(tweets)}: {t[:80]}")
        return True

    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 5)
        await random_mouse_move(page)

        # Light scroll to look human
        for _ in range(random.randint(1, 3)):
            await page.mouse.wheel(0, random.randint(300, 700))
            await jitter(1, 3)

        await page.click(SELECTORS["compose_tweet_btn"], timeout=10000)
        await jitter(1, 2)
        await page.wait_for_selector(SELECTORS["tweet_textarea"], timeout=10000)

        for i, t in enumerate(tweets):
            sel = f'[role="dialog"] [data-testid="tweetTextarea_{i}"]'
            await human_type(page, sel, t)
            await jitter(1, 3)

            # Attach OG image to the FIRST tweet of the thread only — X shows it best there.
            if i == 0 and image_path and image_path.exists():
                try:
                    file_input = None
                    for sel in (
                        '[role="dialog"] [data-testid="fileInput"]',
                        '[data-testid="fileInput"]',
                        '[role="dialog"] input[type="file"]',
                        'input[type="file"][accept*="image"]',
                        'input[type="file"]',
                    ):
                        try:
                            file_input = await page.wait_for_selector(sel, state="attached", timeout=2000)
                            if file_input:
                                logger.debug(f"Found file input via selector: {sel}")
                                break
                        except Exception:
                            continue
                    if file_input:
                        await file_input.set_input_files(str(image_path))
                        await jitter(3, 6)
                        logger.info(f"Image attached to tweet: {image_path.name}")
                    else:
                        logger.warning(f"No file input selector matched — posting WITHOUT image. Take a screenshot to debug X's current DOM.")
                        try:
                            await page.screenshot(path=str(SCREENSHOT_DIR / f"no_file_input_{int(time.time())}.png"))
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning(f"Image upload failed (posting without image): {e}")

            if i < len(tweets) - 1:
                # Add next tweet to thread
                try:
                    await page.click(SELECTORS["thread_add_btn"], timeout=4000)
                    await jitter(0.8, 1.6)
                except Exception as e:
                    logger.warning(f"Add-thread button failed at tweet {i+1}: {e}. Submitting what we have.")
                    break

        clicked = False
        for sel in (SELECTORS["tweet_submit_btn"], SELECTORS["tweet_submit_btn_modal"]):
            try:
                await page.click(sel, timeout=4000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("Could not find tweet submit button.")

        await jitter(3, 6)
        logger.info(f"Posted thread of {len(tweets)} tweet(s). First: {tweets[0][:60]}")
        return True
    except Exception as e:
        ts = int(time.time())
        path = SCREENSHOT_DIR / f"post_fail_{ts}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Thread post failed: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Likes — high-frequency, low-risk engagement
# ---------------------------------------------------------------------------

LIKE_SEARCH_QUERIES = [
    "AI agents",
    "Claude AI",
    "n8n workflow",
    "LLM tools",
    "AI automation",
    "agentic",
    "AI startup",
]


async def like_recent_tweets(page: Page, state: dict[str, Any], max_likes: int, queries: list[str] | None = None) -> int:
    """Search niche, like fresh tweets. Returns count of successful likes."""
    if max_likes <= 0:
        return 0
    pool = queries or LIKE_SEARCH_QUERIES
    query = random.choice(pool)
    url = f"https://x.com/search?q={quote_plus(query)}&f=live"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await jitter(3, 5)
        await page.wait_for_selector(SELECTORS["tweet_card"], timeout=15000)
    except Exception as e:
        logger.warning(f"Like search failed for '{query}': {e}")
        return 0

    cards = await page.query_selector_all(SELECTORS["tweet_card"])
    record_query_run(state, query, "like", len(cards))
    liked = 0
    for card in cards[:25]:
        if liked >= max_likes:
            break
        try:
            link_el = await card.query_selector('a[href*="/status/"]')
            href = await link_el.get_attribute("href") if link_el else None
            if not href:
                continue
            tweet_url = "https://x.com" + href if href.startswith("/") else href
            if tweet_url in state["liked_tweet_ids"]:
                continue

            like_btn = await card.query_selector(SELECTORS["like_btn"])
            if not like_btn:
                continue
            aria = (await like_btn.get_attribute("aria-label")) or ""
            # Skip already-liked tweets
            if "Liked" in aria or "Unlike" in aria:
                continue

            if DRY_RUN:
                logger.info(f"[DRY_RUN] Would like {tweet_url}")
            else:
                await like_btn.scroll_into_view_if_needed()
                await jitter(0.4, 1.0)
                await like_btn.click()
                await jitter(0.8, 2.2)

            state["liked_tweet_ids"].append(tweet_url)
            state["like_history"].insert(0, {
                "tweet_url": tweet_url,
                "liked_at": datetime.now(timezone.utc).isoformat(),
            })
            state["like_history"] = state["like_history"][:200]
            state["liked_tweet_ids"] = state["liked_tweet_ids"][-1000:]
            state["stats"]["total_likes"] = state["stats"].get("total_likes", 0) + 1
            liked += 1
            save_state(state)
        except Exception as e:
            logger.debug(f"Skip like card: {e}")
    logger.info(f"Liked {liked} tweets for query '{query}'")
    return liked


# ---------------------------------------------------------------------------
# Self-engagement scrape — read own profile, find top-performing tweets
# ---------------------------------------------------------------------------

async def check_account_health(page: Page, state: dict[str, Any]) -> dict[str, Any]:
    """Scrape own profile for follower count + suspension/limited warnings.
    Returns {status: ok|warning|critical, follower_count, delta, warnings}.
    On critical, sets state.status = 'paused' so the bot stops acting."""
    if not X_HANDLE:
        return {"status": "ok", "follower_count": None, "delta": 0, "warnings": []}
    health: dict[str, Any] = {"status": "ok", "follower_count": None, "delta": 0, "warnings": []}
    try:
        await page.goto(f"https://x.com/{X_HANDLE}", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 4)

        # Body text scan for known warning phrases
        try:
            body_text = (await page.inner_text("body"))[:4000].lower()
        except Exception:
            body_text = ""
        warning_signals = [
            ("account suspended", "critical"),
            ("your account is locked", "critical"),
            ("verify your account", "warning"),
            ("temporarily limited", "warning"),
            ("unusual activity", "warning"),
            ("we need to verify", "warning"),
        ]
        for phrase, severity in warning_signals:
            if phrase in body_text:
                health["warnings"].append({"phrase": phrase, "severity": severity})
                if severity == "critical":
                    health["status"] = "critical"
                elif health["status"] != "critical":
                    health["status"] = "warning"

        # Follower count — look for anchor with /followers, parse first parent number
        try:
            link = await page.query_selector(f'a[href="/{X_HANDLE}/followers"], a[href="/{X_HANDLE}/verified_followers"]')
            if link:
                txt = (await link.inner_text()).strip()
                # First token is usually the count (e.g. "123 Followers")
                first = txt.split()[0] if txt else "0"
                health["follower_count"] = _parse_count(first)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"Account health scrape failed: {e}")
        return {"status": "ok", "follower_count": None, "delta": 0, "warnings": [{"phrase": "scrape failed", "severity": "info"}]}

    # Compare against last snapshot
    prior = state.get("account_health", {}) or {}
    prior_count = prior.get("follower_count")
    if health["follower_count"] is not None and prior_count is not None:
        delta = health["follower_count"] - prior_count
        health["delta"] = delta
        if delta <= -10:  # sudden drop of 10+
            health["warnings"].append({"phrase": f"follower drop {delta}", "severity": "warning"})
            if health["status"] == "ok":
                health["status"] = "warning"

    health["checked_at"] = datetime.now(timezone.utc).isoformat()
    state["account_health"] = health

    if health["status"] == "critical":
        logger.error(f"ACCOUNT HEALTH CRITICAL: {health['warnings']} — pausing bot.")
        state["status"] = "paused"
    elif health["status"] == "warning":
        logger.warning(f"Account health warning: {health['warnings']}")
    save_state(state)
    return health


async def scrape_own_top_tweets(page: Page, state: dict[str, Any]) -> None:
    """Visit own profile, scrape recent tweets + like counts, store top 5 in state.top_tweets."""
    if not X_HANDLE:
        return
    try:
        await page.goto(f"https://x.com/{X_HANDLE}", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 4)
        await page.wait_for_selector(SELECTORS["tweet_card"], timeout=10000)
        # Scroll to load more
        for _ in range(3):
            await page.mouse.wheel(0, random.randint(500, 900))
            await jitter(1, 2)
        cards = await page.query_selector_all(SELECTORS["tweet_card"])
        scraped: list[dict[str, Any]] = []
        for card in cards[:20]:
            try:
                text_el = await card.query_selector(SELECTORS["tweet_text"])
                text = (await text_el.inner_text()) if text_el else ""
                if not text:
                    continue
                like_el = await card.query_selector(f'{SELECTORS["like_btn"]} span')
                likes = _parse_count((await like_el.inner_text()).strip()) if like_el else 0
                scraped.append({"text": text, "likes": likes})
            except Exception:
                continue
        scraped.sort(key=lambda x: x["likes"], reverse=True)
        state["top_tweets"] = scraped[:5]
        # Engagement learning loop: also capture the bottom 3 as negative reference
        state["bottom_tweets"] = scraped[-3:] if len(scraped) >= 6 else []
        save_state(state)
        if scraped:
            logger.info(
                f"Self-engagement: top={scraped[0]['likes']} likes, "
                f"bottom={scraped[-1]['likes']} likes, n={len(scraped)}"
            )
    except Exception as e:
        logger.warning(f"Self-engagement scrape failed: {e}")


# ---------------------------------------------------------------------------
# Reply discovery & posting
# ---------------------------------------------------------------------------

@dataclass
class TweetCandidate:
    url: str
    text: str
    likes: int
    age_minutes: int = 9999
    element_handle: Any = None


async def discover_reply_candidates(page: Page, query: str) -> list[TweetCandidate]:
    url = f"https://x.com/search?q={quote_plus(query)}&f=live"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await jitter(4, 8)  # longer settle — X's React tree takes a beat
    try:
        await page.wait_for_selector(SELECTORS["tweet_card"], timeout=20000)
    except Exception as e:
        # Detect throttle/error pages and screenshot for debugging
        body_text = ""
        try:
            body_text = (await page.inner_text("body"))[:500]
        except Exception:
            pass
        if any(s in body_text for s in ("Something went wrong", "Try reloading", "Rate limit")):
            logger.warning(f"X showed an error page for '{query}' — likely throttled. Cooling down.")
            state["_cycle_error_count"] = int(state.get("_cycle_error_count", 0)) + 1
            await jitter(30, 60)
        else:
            logger.warning(f"No tweets loaded for query '{query}': {e}")
            state["_cycle_error_count"] = int(state.get("_cycle_error_count", 0)) + 1
        try:
            await page.screenshot(path=str(SCREENSHOT_DIR / f"search_empty_{int(time.time())}.png"))
        except Exception:
            pass
        return []

    # Scroll a bit to load more
    for _ in range(2):
        await page.mouse.wheel(0, random.randint(400, 900))
        await jitter(1, 2)

    cards = await page.query_selector_all(SELECTORS["tweet_card"])
    candidates: list[TweetCandidate] = []
    for card in cards[:12]:
        try:
            # Skip ads
            ad = await card.query_selector(SELECTORS["ad_marker"])
            if ad:
                # placementTracking also matches some non-ads; the safer signal is
                # the literal "Ad" badge inside the card.
                text_node = await card.inner_text()
                if "\nAd\n" in f"\n{text_node}\n":
                    continue

            text_el = await card.query_selector(SELECTORS["tweet_text"])
            text = (await text_el.inner_text()) if text_el else ""
            if not text or len(text) < 20:
                continue

            link_el = await card.query_selector('a[href*="/status/"]')
            href = await link_el.get_attribute("href") if link_el else None
            if not href:
                continue
            tweet_url = "https://x.com" + href if href.startswith("/") else href

            like_el = await card.query_selector(f'{SELECTORS["like_btn"]} span')
            likes_text = (await like_el.inner_text()).strip() if like_el else "0"
            likes = _parse_count(likes_text)

            # Age from <time datetime="...">
            time_el = await card.query_selector("time")
            age_min = 9999
            if time_el:
                dt_attr = await time_el.get_attribute("datetime")
                if dt_attr:
                    try:
                        posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                        age_min = int((datetime.now(timezone.utc) - posted).total_seconds() / 60)
                    except Exception:
                        pass

            candidates.append(TweetCandidate(
                url=tweet_url, text=text, likes=likes,
                age_minutes=age_min, element_handle=card,
            ))
        except Exception as e:
            logger.debug(f"Skipping a card: {e}")

    return candidates


def _parse_count(s: str) -> int:
    s = (s or "").strip().replace(",", "")
    if not s:
        return 0
    try:
        if s.endswith("K"):
            return int(float(s[:-1]) * 1_000)
        if s.endswith("M"):
            return int(float(s[:-1]) * 1_000_000)
        return int(float(s))
    except Exception:
        return 0


async def post_reply(page: Page, candidate: TweetCandidate, reply_text: str) -> bool:
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would reply to {candidate.url}: {reply_text[:80]}")
        return True

    try:
        # Click the tweet to open it (more reliable than scoping reply button on card)
        await page.goto(candidate.url, wait_until="domcontentloaded", timeout=30000)
        await jitter(3, 6)
        await random_mouse_move(page)

        await page.wait_for_selector(SELECTORS["reply_btn"], timeout=10000)
        await page.click(SELECTORS["reply_btn"])
        await jitter(1, 3)
        await page.wait_for_selector(SELECTORS["tweet_textarea"], timeout=10000)
        await human_type(page, SELECTORS["tweet_textarea"], reply_text)
        await jitter(1, 3)

        clicked = False
        for sel in (SELECTORS["tweet_submit_btn"], SELECTORS["tweet_submit_btn_modal"]):
            try:
                await page.click(sel, timeout=4000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("Could not find reply submit button.")

        await jitter(3, 6)
        logger.info(f"Replied to {candidate.url}: {reply_text[:60]}")
        return True
    except Exception as e:
        path = SCREENSHOT_DIR / f"reply_fail_{int(time.time())}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Reply failed: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Quote-tweet flow
# ---------------------------------------------------------------------------

QUOTE_SEARCH_QUERIES = [
    "AI agents", "Claude", "LLM", "RAG", "AI tools", "n8n", "MCP",
    "Cursor", "AI startup", "agentic", "AI workflow",
]


async def discover_quote_candidates(page: Page, query: str) -> list[TweetCandidate]:
    """Find VIRAL fresh tweets to quote-tweet. Different filter than reply: high likes."""
    cands = await discover_reply_candidates(page, query)
    # Quote candidates: 100-10000 likes (viral but not mega), under 4h old
    return [
        c for c in cands
        if 100 <= c.likes <= 10000 and c.age_minutes <= 240
    ]


async def post_quote_tweet(page: Page, candidate: TweetCandidate, text: str) -> bool:
    """Click retweet → choose 'Quote' → type → submit."""
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would quote-tweet {candidate.url}: {text[:80]}")
        return True
    try:
        await page.goto(candidate.url, wait_until="domcontentloaded", timeout=30000)
        await jitter(3, 6)
        await random_mouse_move(page)

        await page.wait_for_selector(SELECTORS["retweet_btn"], timeout=10000)
        await page.click(SELECTORS["retweet_btn"])
        await jitter(0.8, 1.6)

        # The retweet popup has Repost + Quote items. Match by visible text.
        clicked_quote = False
        for selector in (
            'div[role="menuitem"]:has-text("Quote")',
            'div[role="menuitem"] >> text=Quote',
        ):
            try:
                await page.click(selector, timeout=4000)
                clicked_quote = True
                break
            except Exception:
                continue
        if not clicked_quote:
            raise RuntimeError("Could not find Quote menu item.")

        await jitter(1, 2)
        await page.wait_for_selector(SELECTORS["tweet_textarea"], timeout=10000)
        await human_type(page, SELECTORS["tweet_textarea"], text)
        await jitter(1, 3)

        clicked = False
        for sel in (SELECTORS["tweet_submit_btn"], SELECTORS["tweet_submit_btn_modal"]):
            try:
                await page.click(sel, timeout=4000)
                clicked = True
                break
            except Exception:
                continue
        if not clicked:
            raise RuntimeError("Could not find quote submit button.")
        await jitter(3, 6)
        logger.info(f"Quote-tweeted {candidate.url}: {text[:60]}")
        return True
    except Exception as e:
        path = SCREENSHOT_DIR / f"quote_fail_{int(time.time())}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Quote-tweet failed: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Conversation continuation
# ---------------------------------------------------------------------------

async def scrape_own_recent_tweets_with_replies(page: Page, state: dict[str, Any]) -> list[dict[str, Any]]:
    """Scrape your own recent tweets (24h-7d old) and any replies they got."""
    if not X_HANDLE:
        return []
    out: list[dict[str, Any]] = []
    try:
        await page.goto(f"https://x.com/{X_HANDLE}", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 4)
        await page.wait_for_selector(SELECTORS["tweet_card"], timeout=10000)
        cards = await page.query_selector_all(SELECTORS["tweet_card"])
        my_tweets: list[dict[str, Any]] = []
        for card in cards[:10]:
            try:
                text_el = await card.query_selector(SELECTORS["tweet_text"])
                text = (await text_el.inner_text()) if text_el else ""
                link_el = await card.query_selector('a[href*="/status/"]')
                href = await link_el.get_attribute("href") if link_el else None
                if not href:
                    continue
                tweet_url = "https://x.com" + href if href.startswith("/") else href
                time_el = await card.query_selector("time")
                age_min = 9999
                if time_el:
                    dt_attr = await time_el.get_attribute("datetime")
                    if dt_attr:
                        try:
                            posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                            age_min = int((datetime.now(timezone.utc) - posted).total_seconds() / 60)
                        except Exception:
                            pass
                # 24h to 7d old window
                if not (1440 <= age_min <= 10080):
                    continue
                if tweet_url in state.get("responded_thread_ids", []):
                    continue
                my_tweets.append({"url": tweet_url, "text": text, "age_minutes": age_min})
            except Exception:
                continue

        # For each, visit the tweet, scrape the first reply that isn't your own
        for mt in my_tweets[:3]:
            try:
                await page.goto(mt["url"], wait_until="domcontentloaded", timeout=30000)
                await jitter(3, 5)
                await page.wait_for_selector(SELECTORS["tweet_card"], timeout=10000)
                reply_cards = await page.query_selector_all(SELECTORS["tweet_card"])
                # First card is the original tweet; subsequent are replies
                for rc in reply_cards[1:5]:
                    try:
                        author_link = await rc.query_selector('a[href^="/"]')
                        author_href = (await author_link.get_attribute("href")) if author_link else ""
                        if author_href and author_href.lstrip("/").lower() == X_HANDLE.lower():
                            continue  # skip our own
                        reply_text_el = await rc.query_selector(SELECTORS["tweet_text"])
                        reply_text = (await reply_text_el.inner_text()) if reply_text_el else ""
                        if not reply_text or len(reply_text) < 5:
                            continue
                        out.append({
                            "your_tweet_url": mt["url"],
                            "your_tweet": mt["text"][:300],
                            "their_reply": reply_text[:300],
                        })
                        break  # one reply per thread
                    except Exception:
                        continue
            except Exception as e:
                logger.debug(f"Skip thread {mt['url']}: {e}")
        logger.info(f"Conversation continuation: found {len(out)} threads with new replies")
    except Exception as e:
        logger.warning(f"Conversation scrape failed: {e}")
    return out


async def post_follow_up_reply(page: Page, thread_url: str, reply_text: str) -> bool:
    """Reuse the reply infrastructure — we navigate to the thread, click reply, post."""
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would follow-up on {thread_url}: {reply_text[:80]}")
        return True
    try:
        await page.goto(thread_url, wait_until="domcontentloaded", timeout=30000)
        await jitter(3, 5)
        await random_mouse_move(page)
        await page.wait_for_selector(SELECTORS["reply_btn"], timeout=10000)
        await page.click(SELECTORS["reply_btn"])
        await jitter(1, 3)
        await page.wait_for_selector(SELECTORS["tweet_textarea"], timeout=10000)
        await human_type(page, SELECTORS["tweet_textarea"], reply_text)
        await jitter(1, 3)
        for sel in (SELECTORS["tweet_submit_btn"], SELECTORS["tweet_submit_btn_modal"]):
            try:
                await page.click(sel, timeout=4000)
                break
            except Exception:
                continue
        await jitter(3, 6)
        logger.info(f"Follow-up posted on {thread_url}: {reply_text[:60]}")
        return True
    except Exception as e:
        path = SCREENSHOT_DIR / f"followup_fail_{int(time.time())}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Follow-up failed: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Follow discovery & action
# ---------------------------------------------------------------------------

@dataclass
class UserCandidate:
    username: str
    bio: str
    follower_text: str
    element_handle: Any = None


async def discover_followers_of_creator(page: Page, creator_handle: str) -> list[UserCandidate]:
    """Scrape the followers page of a tracked creator — same niche, much higher follow-back rate
    than generic search. Falls back gracefully if X requires auth gate to view."""
    creator_handle = creator_handle.lstrip("@").strip()
    if not creator_handle:
        return []
    url = f"https://x.com/{creator_handle}/followers"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await jitter(3, 5)
        await page.wait_for_selector(SELECTORS["user_cell"], timeout=12000)
    except Exception as e:
        logger.warning(f"Could not load followers of @{creator_handle}: {e}")
        return []

    # Light scroll for more cells
    for _ in range(2):
        await page.mouse.wheel(0, random.randint(500, 900))
        await jitter(1, 2)

    cells = await page.query_selector_all(SELECTORS["user_cell"])
    out: list[UserCandidate] = []
    for cell in cells[:25]:
        try:
            cell_text = await cell.inner_text()
            m = re.search(r"@(\w{2,20})", cell_text)
            if not m:
                continue
            username = m.group(1)
            if username.lower() == creator_handle.lower():
                continue  # skip the creator themselves
            follower_text = ""
            fmatch = re.search(r"([\d.,KMB]+)\s+Followers", cell_text, re.IGNORECASE)
            if fmatch:
                follower_text = fmatch.group(1)
            out.append(UserCandidate(
                username=username,
                bio=cell_text[:200],
                follower_text=follower_text,
                element_handle=cell,
            ))
        except Exception:
            continue
    logger.info(f"Followers-of-creator @{creator_handle}: {len(out)} candidates")
    return out


async def discover_user_candidates(page: Page, query: str) -> list[UserCandidate]:
    url = f"https://x.com/search?q={quote_plus(query)}&f=user"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await jitter(3, 6)
    try:
        await page.wait_for_selector(SELECTORS["user_cell"], timeout=15000)
    except Exception as e:
        logger.warning(f"No user results for '{query}': {e}")
        return []

    cells = await page.query_selector_all(SELECTORS["user_cell"])
    out: list[UserCandidate] = []
    for cell in cells[:15]:
        try:
            cell_text = await cell.inner_text()
            # Extract @handle
            m = re.search(r"@(\w{2,20})", cell_text)
            if not m:
                continue
            username = m.group(1)

            # Crude follower text extraction
            follower_text = ""
            fmatch = re.search(r"([\d.,KMB]+)\s+Followers", cell_text, re.IGNORECASE)
            if fmatch:
                follower_text = fmatch.group(1)

            out.append(UserCandidate(
                username=username,
                bio=cell_text[:200],
                follower_text=follower_text,
                element_handle=cell,
            ))
        except Exception as e:
            logger.debug(f"Skip user cell: {e}")
    return out


async def follow_user(page: Page, user: UserCandidate) -> bool:
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would follow @{user.username}")
        return True

    try:
        # Find a Follow button inside the cell; X uses aria-label="Follow @handle"
        btn = await user.element_handle.query_selector('button[aria-label^="Follow @"]')
        if not btn:
            # Maybe already following — skip
            logger.info(f"No Follow button for @{user.username} (already following?)")
            return False
        await random_mouse_move(page)
        await btn.click()
        await jitter(2, 4)
        logger.info(f"Followed @{user.username} ({user.follower_text} followers)")
        return True
    except Exception as e:
        path = SCREENSHOT_DIR / f"follow_fail_{int(time.time())}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Follow failed for @{user.username}: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Single cycle
# ---------------------------------------------------------------------------

async def run_cycle(state: dict[str, Any]) -> None:
    state["stats"]["cycles_run"] += 1
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    consume_force_new_cycle(state)
    save_state(state)

    posts_made = 0
    replies_made = 0
    follows_made = 0
    likes_made = 0
    quotes_made = 0
    follow_ups_made = 0
    # Errors observed THIS cycle. Bumped when search throttle / empty / X error pages occur.
    state["_cycle_error_count"] = 0

    is_peak = in_peak_hour()
    if not is_peak:
        logger.info(f"Off-peak hour ({datetime.now().hour}) — drafting for your approval, engagement still runs.")

    async with async_playwright() as p:
        browser, context = await launch_browser(p, headless=HEADLESS)
        page = await context.new_page()

        try:
            set_action(state, "Initial human-like delay")
            await long_wait(1, 1, state, "Initial wake-up delay")
            if not await respect_control(state):
                return

            set_action(state, "Selector health check")
            ok = await selector_health_check(page)
            if not ok:
                logger.warning("UI health check failed — skipping all actions this cycle.")
                return

            # Account health check — pauses bot if X shows suspension / limit warnings
            set_action(state, "Checking account health")
            health = await check_account_health(page, state)
            if health["status"] == "critical":
                logger.error("Bot paused due to account health critical — exiting cycle.")
                return
            await jitter(2, 4)

            # Self-engagement scrape (drives top-tweet feedback into next prompt)
            set_action(state, "Scraping own engagement")
            await scrape_own_top_tweets(page, state)
            await jitter(2, 5)

            # Creator intel — port from x-ai. Scrapes tracked creators' top tweets
            # so the LLM has real "what's working in this niche right now" examples.
            if CREATORS_TO_STUDY:
                set_action(state, "Scraping tracked creators for style reference")
                try:
                    await creator_intel.gather_creator_intel(
                        page, CREATORS_TO_STUDY, state, per_creator=5,
                    )
                except Exception as e:
                    logger.warning(f"Creator intel scrape failed (non-fatal): {e}")
                await jitter(2, 5)

            # --- LLM strategy synthesis (the brain) ---
            set_action(state, "Researching trends + synthesizing strategy")
            strategy = await intelligence.synthesize_strategy(
                state, NICHE,
                lambda u, s: call_llm(u, s, state),
            )
            merge_memory(state, strategy)
            logger.info(
                f"Strategy: reply_queries={strategy['reply_queries']} | "
                f"topics={len(strategy['tweet_topics'])} | "
                f"repos={len(strategy['github_repos_to_mention'])}"
            )

            # --- Likes first (low-risk, warms the algo signal) ---
            if MAX_LIKES_PER_CYCLE > 0:
                set_action(state, "Liking niche tweets")
                like_queries = strategy.get("like_queries") or ["AI agents", "LLM", "Claude"]
                likes_made = await like_recent_tweets(page, state, MAX_LIKES_PER_CYCLE, like_queries)
                await long_wait(10, 12, state, "Cooldown after likes")

            # --- Posts (off-peak: drop into draft queue instead of posting) ---
            if not is_peak and MAX_POSTS_PER_CYCLE > 0:
                set_action(state, "Drafting off-peak tweets for your approval")
                drafted = 0
                for t in strategy.get("tweet_topics", [])[:3]:
                    thread = await _gate_with_critic(
                        generator=lambda t=t: generate_trend_thread(t, state),
                        serializer=lambda x: "\n\n".join(x) if x else "",
                        role="tweet",
                        state=state,
                    )
                    if not thread:
                        continue
                    state.setdefault("draft_queue", []).insert(0, {
                        "id": f"draft-{int(time.time()*1000)}-{drafted}",
                        "kind": "trend",
                        "thread": thread,
                        "title": t.get("angle", "")[:120],
                        "source_url": t.get("source_url", ""),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    })
                    state["draft_queue"] = state["draft_queue"][:30]
                    save_state(state)
                    drafted += 1
                if drafted:
                    logger.info(f"Drafted {drafted} tweets to queue (off-peak).")

            if is_peak and MAX_POSTS_PER_CYCLE > 0:
                # --- First: post any drafts you approved on the dashboard ---
                approved = [d for d in state.get("draft_queue", []) if d.get("approved")]
                for d in approved[:MAX_POSTS_PER_CYCLE]:
                    if posts_made >= MAX_POSTS_PER_CYCLE:
                        break
                    if not await respect_control(state):
                        return
                    # Fetch OG image from the draft's source URL (saved when drafted)
                    image_path = None
                    src = d.get("source_url", "")
                    if src:
                        try:
                            image_path = await fetch_og_image(src)
                        except Exception as e:
                            logger.debug(f"OG fetch failed for draft {d.get('id')}: {e}")
                    set_action(state, f"Posting approved draft{' +image' if image_path else ''}")
                    if await post_thread(page, d["thread"], image_path=image_path):
                        posts_made += 1
                        state["stats"]["total_tweets"] += 1
                        state["tweet_history"].insert(0, {
                            "text": "\n---\n".join(d["thread"]),
                            "posted_at": datetime.now(timezone.utc).isoformat(),
                            "news_title": d.get("title", ""),
                            "news_link": d.get("source_url", ""),
                            "thread_length": len(d["thread"]),
                            "kind": "approved_draft",
                        })
                        state["tweet_history"] = state["tweet_history"][:200]
                        # Remove from queue
                        state["draft_queue"] = [x for x in state["draft_queue"] if x.get("id") != d.get("id")]
                        save_state(state)
                    if posts_made < MAX_POSTS_PER_CYCLE:
                        await long_wait(10, 12, state, "Spacing after approved draft")

                # --- Then: top up with fresh generated posts if still slots open ---
                # Build a post queue: strategy topics (trend-driven) FIRST, RSS as fallback.
                post_queue: list[dict[str, Any]] = []

                # 1. LLM-curated trending topics (real GitHub / HN sources)
                for t in strategy.get("tweet_topics", []):
                    post_queue.append({"kind": "trend", "data": t})

                # 2. GitHub repos worth highlighting — synthesize as tweet topics
                for repo in strategy.get("github_repos_to_mention", []):
                    name = repo.get("name", "")
                    if not name:
                        continue
                    post_queue.append({"kind": "repo", "data": {
                        "angle": f"new GitHub repo: {name} - {repo.get('why','')}",
                        "context": repo.get("description", ""),
                        "source_url": repo.get("url", ""),
                        "repo_name": name,
                    }})

                # 3. RSS fallback if strategy is thin
                if len(post_queue) < MAX_POSTS_PER_CYCLE:
                    set_action(state, "Fetching news (fallback)")
                    news = fetch_news(state)
                    for item in news[: MAX_POSTS_PER_CYCLE - len(post_queue)]:
                        post_queue.append({"kind": "rss", "data": item})

                # Shuffle inside each kind class a bit so we don't always lead with trend
                trend_items = [q for q in post_queue if q["kind"] in ("trend", "repo")]
                rss_items   = [q for q in post_queue if q["kind"] == "rss"]
                random.shuffle(trend_items)
                post_queue = trend_items + rss_items

                for i, qitem in enumerate(post_queue[:MAX_POSTS_PER_CYCLE]):
                    if posts_made >= MAX_POSTS_PER_CYCLE:
                        break
                    if not await respect_control(state):
                        return

                    kind = qitem["kind"]
                    data = qitem["data"]
                    set_action(state, f"Generating {kind} thread {i+1}")

                    # Critic-gated generation
                    if kind == "rss":
                        thread = await _gate_with_critic(
                            generator=lambda: generate_thread(data, state),
                            serializer=lambda t: "\n\n".join(t) if t else "",
                            role="tweet",
                            state=state,
                        )
                        title = data.title
                        link = data.link
                    else:
                        thread = await _gate_with_critic(
                            generator=lambda: generate_trend_thread(data, state),
                            serializer=lambda t: "\n\n".join(t) if t else "",
                            role="tweet",
                            state=state,
                        )
                        title = data.get("angle", "")[:120]
                        link = data.get("source_url", "")

                    if not thread:
                        logger.warning(f"Thread generation empty for {kind} — skipping.")
                        if kind == "rss":
                            state["processed_links"].append(data.link)
                            save_state(state)
                        continue

                    # Best-effort OG image fetch from the source URL
                    image_path = None
                    src_url = data.link if kind == "rss" else data.get("source_url", "")
                    if src_url:
                        try:
                            image_path = await fetch_og_image(src_url)
                        except Exception as e:
                            logger.debug(f"OG image fetch failed: {e}")

                    set_action(state, f"Posting {kind} thread {i+1} ({len(thread)} tweet(s)){' +image' if image_path else ''}")
                    if await post_thread(page, thread, image_path=image_path):
                        posts_made += 1
                        state["stats"]["total_tweets"] += 1
                        state["tweet_history"].insert(0, {
                            "text": "\n---\n".join(thread),
                            "posted_at": datetime.now(timezone.utc).isoformat(),
                            "news_title": title,
                            "news_link": link,
                            "thread_length": len(thread),
                            "kind": kind,
                        })
                        state["tweet_history"] = state["tweet_history"][:200]

                        # Track repo so we don't repeat it
                        if kind == "repo" and data.get("repo_name"):
                            record_repo_tracked(state, data["repo_name"])

                    if kind == "rss":
                        state["processed_links"].append(data.link)
                        state["processed_links"] = state["processed_links"][-500:]
                    save_state(state)

                    if i < len(post_queue) - 1 and posts_made < MAX_POSTS_PER_CYCLE:
                        await long_wait(10, 12, state, "Spacing between posts")

            # --- Replies (highest growth lever — do many) ---
            if MAX_REPLIES_PER_CYCLE > 0:
                if not await respect_control(state):
                    return
                # Shorter cooldown for first reply, then space them out
                await long_wait(10, 12, state, "Pre-reply pause")

                # Strategy-driven query pool (LLM-curated), falls back to baseline
                reply_pool = strategy.get("reply_queries") or REPLY_SEARCH_QUERIES
                used_queries: set[str] = set()
                for r_idx in range(MAX_REPLIES_PER_CYCLE):
                    if not await respect_control(state):
                        return
                    available = [q for q in reply_pool if q not in used_queries]
                    if not available:
                        available = reply_pool
                    query = random.choice(available)
                    used_queries.add(query)

                    set_action(state, f"Reply {r_idx+1}/{MAX_REPLIES_PER_CYCLE}: searching '{query}'")
                    cands = await discover_reply_candidates(page, query)
                    record_query_run(state, query, "reply", len(cands))
                    # Filter: fresh (under 90 min), rising (5-500 likes — avoid mega-viral), not replied
                    cands = [
                        c for c in cands
                        if 5 <= c.likes <= 500
                        and c.age_minutes <= 90
                        and c.url not in state["replied_tweet_ids"]
                    ]
                    if not cands:
                        logger.info(f"No fresh reply candidates for '{query}'.")
                        continue

                    # Smart analyzer: classify each candidate + pick best (#2, #8, #9 combined)
                    cands.sort(key=lambda x: x.likes, reverse=True)
                    top5 = cands[:5]
                    cand_dicts = [
                        {"idx": i, "text": c.text, "likes": c.likes, "age_minutes": c.age_minutes}
                        for i, c in enumerate(top5)
                    ]
                    analysis = await intelligence.analyze_reply_candidates(
                        cand_dicts, NICHE,
                        lambda u, s: call_llm(u, s, state),
                    )
                    if not analysis:
                        logger.info(f"Analyzer rejected all candidates for '{query}'.")
                        continue
                    best_idx = analysis["best_idx"]
                    if best_idx is None or best_idx >= len(top5):
                        continue
                    best = top5[best_idx]
                    style = analysis.get("reply_style", "offer_specific_insight")
                    # Pull this candidate's classification/sentiment
                    info = next((x for x in analysis.get("all", []) if x.get("idx") == best_idx), {})
                    classification = info.get("type", "genuine")
                    sentiment = info.get("sentiment", "neutral")
                    logger.info(
                        f"Reply analyzer picked idx={best_idx} "
                        f"(type={classification}, sentiment={sentiment}, style={style})"
                    )

                    set_action(state, f"Generating reply {r_idx+1}")
                    # Critic-gated reply generation
                    reply = await _gate_with_critic(
                        generator=lambda: generate_reply(
                            best.text, state,
                            classification=classification,
                            sentiment=sentiment,
                            reply_style=style,
                        ),
                        serializer=lambda x: x or "",
                        role="reply",
                        state=state,
                    )
                    if not reply:
                        continue

                    set_action(state, f"Posting reply {r_idx+1}")
                    if await post_reply(page, best, reply):
                        replies_made += 1
                        state["stats"]["total_replies"] += 1
                        state["replied_tweet_ids"].append(best.url)
                        state["replied_tweet_ids"] = state["replied_tweet_ids"][-500:]
                        state["reply_history"].insert(0, {
                            "reply_text": reply,
                            "original_tweet_url": best.url,
                            "original_tweet_text": best.text[:200],
                            "posted_at": datetime.now(timezone.utc).isoformat(),
                        })
                        state["reply_history"] = state["reply_history"][:200]
                        save_state(state)

                    if r_idx < MAX_REPLIES_PER_CYCLE - 1:
                        await long_wait(10, 12, state, "Spacing between replies")

            # --- Quote-tweet (1 per cycle, only peak hours) ---
            quotes_made = 0
            if is_peak and MAX_QUOTES_PER_CYCLE > 0:
                if not await respect_control(state):
                    return
                await long_wait(10, 12, state, "Cooldown before quote-tweet")
                q_query = random.choice(QUOTE_SEARCH_QUERIES)
                set_action(state, f"Searching viral tweets to quote: '{q_query}'")
                q_cands = await discover_quote_candidates(page, q_query)
                q_cands = [c for c in q_cands if c.url not in state.get("replied_tweet_ids", [])]
                if q_cands:
                    q_cands.sort(key=lambda x: x.likes, reverse=True)
                    target = q_cands[0]
                    set_action(state, "Generating quote-tweet")
                    quote_text = await _gate_with_critic(
                        generator=lambda: generate_quote(target.text, state),
                        serializer=lambda x: x or "",
                        role="quote",
                        state=state,
                    )
                    if quote_text:
                        set_action(state, "Posting quote-tweet")
                        if await post_quote_tweet(page, target, quote_text):
                            quotes_made += 1
                            state["stats"]["total_quotes"] = state["stats"].get("total_quotes", 0) + 1
                            state["quote_history"].insert(0, {
                                "quote_text": quote_text,
                                "original_tweet_url": target.url,
                                "original_tweet_text": target.text[:200],
                                "original_likes": target.likes,
                                "posted_at": datetime.now(timezone.utc).isoformat(),
                            })
                            state["quote_history"] = state["quote_history"][:200]
                            state["replied_tweet_ids"].append(target.url)
                            save_state(state)
                else:
                    logger.info(f"No quote candidates for '{q_query}'.")

            # --- Conversation continuation: follow up on replies to your own tweets ---
            if MAX_FOLLOW_UPS_PER_CYCLE > 0:
                if not await respect_control(state):
                    return
                await long_wait(10, 12, state, "Cooldown before follow-ups")
                set_action(state, "Scanning own tweets for new replies")
                threads = await scrape_own_recent_tweets_with_replies(page, state)
                follow_ups_made = 0
                for th in threads[:MAX_FOLLOW_UPS_PER_CYCLE]:
                    if not await respect_control(state):
                        return
                    set_action(state, "Generating follow-up reply")
                    # Quick sentiment check via reply analyzer style (reuse for sentiment)
                    sentiment_check = await intelligence.analyze_reply_candidates(
                        [{"idx": 0, "text": th["their_reply"], "likes": 1, "age_minutes": 60}],
                        NICHE,
                        lambda u, s: call_llm(u, s, state),
                    )
                    info = (sentiment_check or {}).get("all", [{}])[0] if sentiment_check else {}
                    sentiment = info.get("sentiment", "neutral")
                    if info.get("type") in ("spam", "ragebait"):
                        logger.info(f"Skipping follow-up — hostile/spam: {th['their_reply'][:60]}")
                        state["responded_thread_ids"].append(th["your_tweet_url"])
                        save_state(state)
                        continue

                    reply = await _gate_with_critic(
                        generator=lambda: generate_follow_up(
                            th["your_tweet"], th["their_reply"], sentiment, state
                        ),
                        serializer=lambda x: x or "",
                        role="follow_up",
                        state=state,
                    )
                    if not reply:
                        state["responded_thread_ids"].append(th["your_tweet_url"])
                        save_state(state)
                        continue
                    set_action(state, "Posting follow-up reply")
                    if await post_follow_up_reply(page, th["your_tweet_url"], reply):
                        follow_ups_made += 1
                        state["stats"]["total_follow_ups"] = state["stats"].get("total_follow_ups", 0) + 1
                        state["follow_up_history"].insert(0, {
                            "your_tweet": th["your_tweet"][:200],
                            "their_reply": th["their_reply"][:200],
                            "your_followup": reply,
                            "thread_url": th["your_tweet_url"],
                            "posted_at": datetime.now(timezone.utc).isoformat(),
                        })
                        state["follow_up_history"] = state["follow_up_history"][:100]
                        state["responded_thread_ids"].append(th["your_tweet_url"])
                        state["responded_thread_ids"] = state["responded_thread_ids"][-300:]
                        save_state(state)
                    if follow_ups_made < MAX_FOLLOW_UPS_PER_CYCLE:
                        await long_wait(10, 12, state, "Spacing between follow-ups")

            # --- Follow ---
            if follows_made < MAX_FOLLOWS_PER_CYCLE:
                if not await respect_control(state):
                    return
                await long_wait(10, 12, state, "Cooldown before follow discovery")

                # 50/50 split each cycle: follower-of-creator vs query search.
                # Follower-of-followers tends to convert 2-3x better than generic search.
                use_creator_followers = bool(CREATORS_TO_STUDY) and random.random() < 0.6
                if use_creator_followers:
                    creator = random.choice(CREATORS_TO_STUDY)
                    set_action(state, f"Discovering followers of @{creator}")
                    users = await discover_followers_of_creator(page, creator)
                    record_query_run(state, f"followers-of:@{creator}", "follow", len(users))
                else:
                    follow_pool = strategy.get("follow_queries") or FOLLOW_SEARCH_QUERIES
                    query = random.choice(follow_pool)
                    set_action(state, f"Searching users for '{query}'")
                    users = await discover_user_candidates(page, query)
                    record_query_run(state, query, "follow", len(users))
                users = [u for u in users if u.username not in state["followed_usernames"]]

                target = random.randint(1, MAX_FOLLOWS_PER_CYCLE)
                for u in users[:target]:
                    if not await respect_control(state):
                        return
                    set_action(state, f"Following @{u.username}")
                    if await follow_user(page, u):
                        follows_made += 1
                        state["stats"]["total_follows"] += 1
                        state["followed_usernames"].append(u.username)
                        state["followed_usernames"] = state["followed_usernames"][-1000:]
                        state["follow_history"].insert(0, {
                            "username": u.username,
                            "followed_at": datetime.now(timezone.utc).isoformat(),
                            "follower_count": u.follower_text,
                        })
                        state["follow_history"] = state["follow_history"][:200]
                        save_state(state)
                    if follows_made >= MAX_FOLLOWS_PER_CYCLE:
                        break
                    await long_wait(10, 12, state, "Spacing between follows")

            # Adaptive cooldown counter: bump if 2+ errors this cycle, reset if clean
            cycle_errors = int(state.get("_cycle_error_count", 0) or 0)
            prev_consec = int(state.get("consecutive_error_cycles", 0) or 0)
            if cycle_errors >= 2:
                state["consecutive_error_cycles"] = prev_consec + 1
                logger.warning(
                    f"Cycle had {cycle_errors} errors — consecutive_error_cycles "
                    f"now {state['consecutive_error_cycles']} (next cycle cooldowns x{_adaptive_multiplier(state):.0f})"
                )
            elif prev_consec > 0:
                logger.info(f"Clean cycle — resetting consecutive_error_cycles from {prev_consec} to 0")
                state["consecutive_error_cycles"] = 0
            save_state(state)

            logger.info(
                f"Cycle complete. Posts: {posts_made} | Replies: {replies_made} | "
                f"Likes: {likes_made} | Quotes: {quotes_made} | "
                f"Follow-ups: {follow_ups_made} | Follows: {follows_made} | "
                f"LLM calls: {state['stats']['llm_calls_today']} | Errors: {cycle_errors} | "
                f"Peak hour: {is_peak} | Next cycle in ~{CYCLE_INTERVAL_HOURS}h"
            )

        finally:
            try:
                await context.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

async def main_loop() -> None:
    state = load_state()
    logger.info("=" * 60)
    logger.info("X Automation Bot starting")
    logger.info(f"DRY_RUN={DRY_RUN} HEADLESS={HEADLESS} LLM_PROVIDER={LLM_PROVIDER}")
    logger.info("=" * 60)

    if not COOKIES_PATH.exists():
        logger.error(
            "cookies.json not found. Run: HEADLESS=false python x_automation_bot.py login"
        )
        return

    while True:
        state = load_state()
        if state.get("status") == "stopped":
            logger.info("Status is 'stopped' — exiting main loop.")
            break

        try:
            await run_cycle(state)
        except Exception as e:
            logger.exception(f"Cycle crashed: {e}")

        # Reset daily LLM counter at midnight (rough)
        try:
            last = state.get("last_run")
            if last and datetime.fromisoformat(last).date() != datetime.now(timezone.utc).date():
                state["stats"]["llm_calls_today"] = 0
        except Exception:
            pass

        # Compute next cycle time with jitter
        jitter_minutes = random.uniform(-20, 20)
        sleep_seconds = CYCLE_INTERVAL_HOURS * 3600 + jitter_minutes * 60
        next_time = datetime.now(timezone.utc) + timedelta(seconds=sleep_seconds)
        state["next_cycle_at"] = next_time.isoformat()
        set_action(state, f"Waiting for next cycle (~{CYCLE_INTERVAL_HOURS}h)")
        save_state(state)

        end = time.monotonic() + sleep_seconds
        while time.monotonic() < end:
            flag = check_control_flag()
            if flag == "stopped":
                logger.info("Stop flag during sleep — exiting.")
                return
            if check_force_new_cycle():
                logger.info("Force-new-cycle flag set — starting next cycle immediately.")
                # Consume the flag here so the next cycle doesn't immediately re-trigger
                fresh = load_state()
                consume_force_new_cycle(fresh)
                break
            await asyncio.sleep(min(5, end - time.monotonic()))


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        asyncio.run(login_flow())
        return
    asyncio.run(main_loop())


if __name__ == "__main__":
    cli()
