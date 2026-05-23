"""
Creator intelligence — port of the most useful idea from melnikoff-oleg/x-ai.

Track a configurable list of top creators in your niche. Each cycle, scrape
their recent best-performing tweets and feed them to the LLM as a "what's
working RIGHT NOW for accounts like mine" reference. Free, no Apify required.
"""
from __future__ import annotations

import logging
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote_plus

logger = logging.getLogger("x_bot.creator_intel")


@dataclass
class CreatorTweet:
    handle: str
    text: str
    likes: int
    replies: int
    url: str
    age_minutes: int


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


async def scrape_creator_top_tweets(page, handle: str, max_tweets: int = 10) -> list[CreatorTweet]:
    """Visit @handle, grab the most recent ~10 tweets sorted by likes."""
    handle = handle.lstrip("@").strip()
    if not handle:
        return []
    url = f"https://x.com/{handle}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector('[data-testid="tweet"]', timeout=12000)
        # Light scroll to load a few more
        for _ in range(2):
            await page.mouse.wheel(0, random.randint(500, 900))
            await page.wait_for_timeout(random.randint(800, 1500))
        cards = await page.query_selector_all('[data-testid="tweet"]')
    except Exception as e:
        logger.warning(f"Failed to load @{handle}: {e}")
        return []

    out: list[CreatorTweet] = []
    for card in cards[:max_tweets * 2]:
        try:
            # Skip pinned + retweeted-from-others — we only want THEIR original tweets
            text_el = await card.query_selector('[data-testid="tweetText"]')
            text = (await text_el.inner_text()) if text_el else ""
            if not text or len(text) < 30:
                continue

            link_el = await card.query_selector('a[href*="/status/"]')
            href = await link_el.get_attribute("href") if link_el else None
            if not href:
                continue
            tweet_url = "https://x.com" + href if href.startswith("/") else href
            # Filter to tweets BY this user (URL contains /<handle>/status/)
            if f"/{handle}/status/" not in tweet_url.lower():
                continue

            like_el = await card.query_selector('[data-testid="like"] span')
            likes = _parse_count((await like_el.inner_text()).strip()) if like_el else 0

            reply_el = await card.query_selector('[data-testid="reply"] span')
            replies = _parse_count((await reply_el.inner_text()).strip()) if reply_el else 0

            time_el = await card.query_selector("time")
            age_min = 99999
            if time_el:
                dt_attr = await time_el.get_attribute("datetime")
                if dt_attr:
                    try:
                        posted = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                        age_min = int((datetime.now(timezone.utc) - posted).total_seconds() / 60)
                    except Exception:
                        pass

            out.append(CreatorTweet(
                handle=handle, text=text, likes=likes,
                replies=replies, url=tweet_url, age_minutes=age_min,
            ))
        except Exception:
            continue

    # Top by likes within the window
    out.sort(key=lambda x: x.likes, reverse=True)
    return out[:max_tweets]


async def gather_creator_intel(
    page,
    creators: list[str],
    state: dict[str, Any],
    per_creator: int = 5,
) -> list[CreatorTweet]:
    """Collect top tweets from all tracked creators. Returns a flat list ranked by likes."""
    all_tweets: list[CreatorTweet] = []
    for h in creators[:8]:  # cap so cycles don't run forever
        try:
            tw = await scrape_creator_top_tweets(page, h, max_tweets=per_creator)
            all_tweets.extend(tw)
            logger.info(f"Creator @{h}: {len(tw)} tweets (top={tw[0].likes if tw else 0} likes)")
        except Exception as e:
            logger.warning(f"Creator @{h} scrape error: {e}")

    # Sort globally by likes — best examples first
    all_tweets.sort(key=lambda x: x.likes, reverse=True)
    # Persist a compact snapshot in state for the dashboard
    state["creator_intel"] = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "creators": creators,
        "top_examples": [
            {"handle": t.handle, "text": t.text[:300], "likes": t.likes,
             "replies": t.replies, "url": t.url, "age_minutes": t.age_minutes}
            for t in all_tweets[:15]
        ],
    }
    return all_tweets


def format_creator_examples(state: dict[str, Any], n: int = 5) -> str:
    """Pretty-print the top creator examples for injection into LLM prompts."""
    ci = state.get("creator_intel", {}) or {}
    examples = ci.get("top_examples", [])
    if not examples:
        return "(no creator examples yet)"
    lines = []
    for ex in examples[:n]:
        text = (ex.get("text") or "").replace("\n", " ")[:240]
        lines.append(f"  @{ex.get('handle')} ({ex.get('likes')} likes): {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tweet style rotation — content variety, port of x-ai's 60/30/10 weighting
# ---------------------------------------------------------------------------

STYLE_MODES = [
    ("hook_driven",
     "Open with a bold claim or counterintuitive observation. One sentence, max 80 chars. Then evidence."),
    ("personal_story",
     "Lead with 'I' or 'we'. A real builder anecdote — debugging, shipping, breaking something."),
    ("contrarian_take",
     "Push back against conventional wisdom. Name what 'everyone' is saying and disagree specifically."),
    ("listicle",
     "Short numbered observation list. 3-5 items. Each item a complete thought, no fluff."),
    ("question_led",
     "Open with a pointed question that frames the rest. Not 'what do you think?' — a real curiosity."),
    ("tool_comparison",
     "Compare two specific tools/approaches. Name both. State which one you actually use and why."),
]

# Weighted: hook 30 / personal 20 / contrarian 20 / listicle 10 / question 10 / comparison 10
STYLE_WEIGHTS = [30, 20, 20, 10, 10, 10]


def pick_style_mode() -> tuple[str, str]:
    """Returns (mode_name, mode_instructions). Weighted random."""
    idx = random.choices(range(len(STYLE_MODES)), weights=STYLE_WEIGHTS, k=1)[0]
    return STYLE_MODES[idx]
