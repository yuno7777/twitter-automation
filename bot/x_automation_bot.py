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
from typing import Any
from urllib.parse import quote_plus

import feedparser
from dotenv import load_dotenv
from playwright.async_api import BrowserContext, Page, async_playwright

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

CYCLE_INTERVAL_HOURS = 5
MAX_POSTS_PER_CYCLE = 3
MAX_REPLIES_PER_CYCLE = 1
MAX_FOLLOWS_PER_CYCLE = 2

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
    "AI automation tools",
    "agentic AI",
    "LLM workflow",
    "AI SaaS founders",
    "machine learning engineers",
    "AI agents 2025",
    "Claude Gemini GPT",
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
    "tweet_textarea": '[data-testid="tweetTextarea_0"]',
    "tweet_submit_btn": '[data-testid="tweetButtonInline"]',
    "tweet_submit_btn_modal": '[data-testid="tweetButton"]',
    "tweet_card": '[data-testid="tweet"]',
    "tweet_text": '[data-testid="tweetText"]',
    "reply_btn": '[data-testid="reply"]',
    "like_btn": '[data-testid="like"]',
    "user_cell": '[data-testid="UserCell"]',
    "ad_marker": '[data-testid="placementTracking"]',
}

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

DEFAULT_STATE: dict[str, Any] = {
    "status": "running",        # running | paused | stopped
    "current_action": "idle",
    "next_cycle_at": None,
    "processed_links": [],
    "replied_tweet_ids": [],
    "followed_usernames": [],
    "tweet_history": [],
    "reply_history": [],
    "follow_history": [],
    "stats": {
        "total_tweets": 0,
        "total_replies": 0,
        "total_follows": 0,
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
# LLM wrapper with Groq -> Gemini fallback
# ---------------------------------------------------------------------------

_groq_client = None
_gemini_configured = False


def _get_groq():
    global _groq_client
    if _groq_client is None and GROQ_API_KEY:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def _configure_gemini():
    global _gemini_configured
    if not _gemini_configured and GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        _gemini_configured = True


async def call_llm(user_prompt: str, system_prompt: str, state: dict[str, Any]) -> str | None:
    """Try Groq, then Gemini. Returns None if both fail."""
    state["stats"]["llm_calls_today"] = state["stats"].get("llm_calls_today", 0) + 1

    # Determine order based on configured primary provider
    primary = LLM_PROVIDER if LLM_PROVIDER in ("groq", "gemini") else "groq"
    order = ["groq", "gemini"] if primary == "groq" else ["gemini", "groq"]

    for provider in order:
        try:
            if provider == "groq":
                client = _get_groq()
                if client is None:
                    logger.warning("Groq API key not set, skipping Groq.")
                    continue
                resp = await asyncio.to_thread(
                    client.chat.completions.create,
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.85,
                    max_tokens=400,
                )
                return resp.choices[0].message.content.strip()
            else:
                _configure_gemini()
                if not GEMINI_API_KEY:
                    logger.warning("Gemini API key not set, skipping Gemini.")
                    continue
                import google.generativeai as genai
                model = genai.GenerativeModel("gemini-1.5-flash")
                result = await asyncio.to_thread(
                    model.generate_content, f"{system_prompt}\n\n{user_prompt}"
                )
                return (result.text or "").strip()
        except Exception as e:
            logger.warning(f"LLM provider '{provider}' failed: {e}")
            await asyncio.sleep(5)

    logger.error("All LLM providers failed.")
    return None


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


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


async def long_wait(min_min: float, max_min: float, state: dict[str, Any], reason: str) -> None:
    minutes = random.uniform(min_min, max_min)
    seconds = minutes * 60
    set_action(state, f"{reason} (~{int(minutes)} min)")
    logger.info(f"Sleeping {minutes:.1f} min — {reason}")
    end = time.monotonic() + seconds
    # Check control flag every 30s
    while time.monotonic() < end:
        if check_control_flag() == "stopped":
            logger.info("Stop flag detected during long wait — aborting.")
            return
        await asyncio.sleep(min(30, end - time.monotonic()))


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

async def generate_tweet(item: NewsItem, state: dict[str, Any]) -> str | None:
    template = load_prompt("tweet_prompt")
    user_prompt = template.format(
        title=item.title,
        summary=item.summary,
        source=item.source,
        link=item.link,
    )
    text = await call_llm(user_prompt, "You write elite high-engagement X tweets.", state)
    if not text:
        return None
    text = strip_markdown(text).strip('"').strip("'")
    if len(text) > 280:
        text = text[:277].rstrip() + "..."
    return text


async def generate_reply(tweet_text: str, state: dict[str, Any]) -> str | None:
    template = load_prompt("reply_prompt")
    user_prompt = template.format(tweet_text=tweet_text)
    text = await call_llm(user_prompt, "You write thoughtful X replies.", state)
    if not text:
        return None
    text = strip_markdown(text).strip('"').strip("'")
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
    if DRY_RUN:
        logger.info(f"[DRY_RUN] Would post tweet: {text[:80]}...")
        return True

    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        await jitter(2, 5)
        await random_mouse_move(page)

        # Scroll a bit to simulate reading
        for _ in range(random.randint(1, 3)):
            await page.mouse.wheel(0, random.randint(300, 700))
            await jitter(1, 3)

        await page.click(SELECTORS["compose_tweet_btn"], timeout=10000)
        await jitter(1, 2)
        await page.wait_for_selector(SELECTORS["tweet_textarea"], timeout=10000)
        await human_type(page, SELECTORS["tweet_textarea"], text)
        await jitter(1, 3)

        # Try modal submit first, then inline
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
        logger.info(f"Posted tweet: {text[:60]}...")
        return True
    except Exception as e:
        ts = int(time.time())
        path = SCREENSHOT_DIR / f"post_fail_{ts}.png"
        try:
            await page.screenshot(path=str(path))
        except Exception:
            pass
        logger.warning(f"Tweet post failed: {e}. Screenshot: {path}")
        return False


# ---------------------------------------------------------------------------
# Reply discovery & posting
# ---------------------------------------------------------------------------

@dataclass
class TweetCandidate:
    url: str
    text: str
    likes: int
    element_handle: Any = None


async def discover_reply_candidates(page: Page, query: str) -> list[TweetCandidate]:
    url = f"https://x.com/search?q={quote_plus(query)}&f=live"
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await jitter(3, 6)
    try:
        await page.wait_for_selector(SELECTORS["tweet_card"], timeout=15000)
    except Exception as e:
        logger.warning(f"No tweets loaded for query '{query}': {e}")
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

            candidates.append(TweetCandidate(
                url=tweet_url, text=text, likes=likes, element_handle=card
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
# Follow discovery & action
# ---------------------------------------------------------------------------

@dataclass
class UserCandidate:
    username: str
    bio: str
    follower_text: str
    element_handle: Any = None


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
    save_state(state)

    posts_made = 0
    replies_made = 0
    follows_made = 0

    async with async_playwright() as p:
        browser, context = await launch_browser(p, headless=HEADLESS)
        page = await context.new_page()

        try:
            set_action(state, "Initial human-like delay")
            await long_wait(3, 10, state, "Initial wake-up delay")
            if not await respect_control(state):
                return

            # Health check
            set_action(state, "Selector health check")
            ok = await selector_health_check(page)
            if not ok:
                logger.warning("UI health check failed — skipping posting this cycle.")

            # --- Posts ---
            set_action(state, "Fetching news")
            news = fetch_news(state)
            news_to_post = news[:MAX_POSTS_PER_CYCLE]

            for i, item in enumerate(news_to_post):
                if posts_made >= MAX_POSTS_PER_CYCLE:
                    break
                if not await respect_control(state):
                    return

                set_action(state, f"Generating tweet {i+1}/{len(news_to_post)}")
                tweet = await generate_tweet(item, state)
                if not tweet:
                    logger.warning("Tweet generation returned None — skipping.")
                    state["processed_links"].append(item.link)
                    save_state(state)
                    continue

                set_action(state, f"Posting tweet {i+1}")
                if ok and await post_tweet(page, tweet):
                    posts_made += 1
                    state["stats"]["total_tweets"] += 1
                    state["tweet_history"].insert(0, {
                        "text": tweet,
                        "posted_at": datetime.now(timezone.utc).isoformat(),
                        "news_title": item.title,
                        "news_link": item.link,
                    })
                    state["tweet_history"] = state["tweet_history"][:200]

                state["processed_links"].append(item.link)
                state["processed_links"] = state["processed_links"][-500:]
                save_state(state)

                # Spacing between posts
                if i < len(news_to_post) - 1 and posts_made < MAX_POSTS_PER_CYCLE:
                    await long_wait(12, 35, state, "Spacing between posts")

            # --- Reply ---
            if replies_made < MAX_REPLIES_PER_CYCLE and ok:
                if not await respect_control(state):
                    return
                await long_wait(15, 40, state, "Cooldown before reply discovery")

                query = random.choice(REPLY_SEARCH_QUERIES)
                set_action(state, f"Searching replies for '{query}'")
                cands = await discover_reply_candidates(page, query)
                cands = [
                    c for c in cands
                    if c.likes >= 2 and c.url not in state["replied_tweet_ids"]
                ]
                if cands:
                    best = max(cands, key=lambda x: x.likes)
                    set_action(state, "Generating reply")
                    reply = await generate_reply(best.text, state)
                    if reply:
                        set_action(state, "Posting reply")
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
                else:
                    logger.info(f"No suitable reply candidates for '{query}'.")

            # --- Follow ---
            if follows_made < MAX_FOLLOWS_PER_CYCLE and ok:
                if not await respect_control(state):
                    return
                await long_wait(25, 60, state, "Cooldown before follow discovery")

                query = random.choice(FOLLOW_SEARCH_QUERIES)
                set_action(state, f"Searching users for '{query}'")
                users = await discover_user_candidates(page, query)
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
                    await long_wait(20, 30, state, "Spacing between follows")

            # Cycle summary
            logger.info(
                f"Cycle complete. Posts: {posts_made} | Replies: {replies_made} | "
                f"Follows: {follows_made} | LLM calls: {state['stats']['llm_calls_today']} | "
                f"Next cycle in ~{CYCLE_INTERVAL_HOURS} hours"
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
            await asyncio.sleep(min(60, end - time.monotonic()))


def cli() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        asyncio.run(login_flow())
        return
    asyncio.run(main_loop())


if __name__ == "__main__":
    cli()
