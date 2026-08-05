"""
Trend discovery + strategy synthesis.

Fetches raw signals from multiple sources in parallel:
1. GitHub trending repos (API)
2. HackerNews stories via Algolia search (full-text, date-filtered)
3. Reddit hot posts with comment enrichment (free JSON API)
4. AI newsletter RSS feeds
5. Polymarket prediction markets (free, no auth)
6. YouTube trending AI videos (optional, needs YOUTUBE_API_KEY)

Hands signals + bot memory to an LLM for structured strategy output.
Designed to be called once per cycle. ~1 LLM call. Negligible cost on Groq free tier.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

import httpx

logger = logging.getLogger("x_bot.intel")

# ---------------------------------------------------------------------------
# Raw signal fetchers
# ---------------------------------------------------------------------------

_GITHUB_TOPICS = [
    "ai-agents", "agentic", "llm", "agents", "rag",
    "claude", "gpt", "openai", "anthropic", "agentic-ai",
    "autonomous-agents", "ai-tools", "multi-agent",
]

# Tweetable AI/tech keyword cues for HN / Reddit filtering
_AI_HINT_RE = re.compile(
    r"\b(ai|agent|llm|gpt|claude|gemini|openai|anthropic|rag|model|"
    r"transformer|fine-?tun|prompt|inference|embed|vector|neural|"
    r"agentic|autonomous|copilot|cursor|n8n|langchain|langgraph|"
    r"mcp|tool[- ]use|fine-?tuning|hugging\s*face|ollama)\b",
    re.IGNORECASE,
)

# Words to skip when extracting trending terms — generic English / common verbs
_STOPWORDS = {
    "the","a","an","is","are","was","were","be","been","being","of","to","in","on","at",
    "for","with","by","from","up","down","out","over","under","again","further","then",
    "once","here","there","when","where","why","how","all","any","both","each","few",
    "more","most","other","some","such","no","nor","not","only","own","same","so","than",
    "too","very","s","t","can","will","just","don","should","now","new","update","release",
    "released","launches","launched","announced","announcing","intro","introducing","this",
    "that","these","those","my","your","our","their","its","his","her","they","them","we",
    "you","i","he","she","it","ai","gpt","llm","best","top","good","great","amazing","cool",
    "show","hn","ask","tell","reddit","post","posts","using","use","using","build","built",
    "make","made","get","gets","got","run","runs","running","ran","work","works","worked",
    "play","plays","played","try","tried","first","second","third","next","last","more",
    "many","much","most","because","while","through","during","before","after","above",
    "below","between","into","onto","upon","since","until","without","within","across",
    "without","model","models","tool","tools","day","days","week","weeks","month","months",
    "year","years","time","times","one","two","three","four","five","six","seven","eight",
    "nine","ten","100","1000","official","open","source","free","paid","review","tutorial",
}

# Search noise words — stripped from queries before sending to APIs
# (Inspired by last30days-skill query.py + reddit.py)
_SEARCH_NOISE = frozenset({
    "best", "top", "good", "great", "awesome", "killer",
    "latest", "new", "news", "update", "updates",
    "trending", "hottest", "popular",
    "practices", "features", "tips",
    "recommendations", "advice",
    "methods", "strategies", "approaches",
    "how", "to", "the", "a", "an", "for", "with",
    "of", "in", "on", "is", "are", "what", "which",
    "guide", "tutorial", "using",
})


def _extract_core_subject(topic: str) -> str:
    """Extract core subject from a verbose query by stripping noise words.

    Inspired by last30days-skill's query.extract_core_subject().
    Keeps product names, tool names, and entity strings intact.
    E.g. 'best AI agents for automation' -> 'AI agents automation'
    """
    words = topic.strip().split()
    kept = [w for w in words if w.lower() not in _SEARCH_NOISE]
    return " ".join(kept) if kept else topic.strip()


def _flatten_query_for_algolia(query: str) -> str:
    """Flatten hyphens and commas for Algolia search.

    Inspired by last30days hackernews.py — hyphens and commas tokenize
    awkwardly in Algolia, so 'ts-bun-node' becomes 'ts bun node'.
    """
    return re.sub(r"[-_,]", " ", query).strip()


def token_overlap_relevance(topic: str, text: str) -> float:
    """Score how relevant a piece of text is to a topic using token overlap.

    Inspired by last30days-skill's relevance.py. Returns a score 0.0-1.0
    based on the Jaccard-like overlap between topic tokens and text tokens.
    Used to prevent off-topic viral content from polluting signal quality.
    """
    topic_tokens = {w.lower() for w in re.findall(r"\w{3,}", topic)} - _SEARCH_NOISE
    text_tokens = {w.lower() for w in re.findall(r"\w{3,}", text)}
    if not topic_tokens:
        return 1.0  # No meaningful tokens → can't judge, let it through
    overlap = topic_tokens & text_tokens
    # Weighted: how many of our topic words appear in the text?
    return len(overlap) / len(topic_tokens)


def _deduplicate_cross_source(
    signals: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Merge duplicate stories that appear across multiple sources.

    Inspired by last30days-skill's cluster.py. Uses title-token overlap
    to detect when the same story appears on Reddit, HN, and newsletters.
    Adds a 'also_on' field to surviving items and removes duplicates.
    """
    # Build a flat list of all items with their source tag
    all_items: list[tuple[str, int, dict[str, Any]]] = []
    for source, items in signals.items():
        for idx, item in enumerate(items):
            all_items.append((source, idx, item))

    # Simple O(n²) pairwise comparison — fine for <100 items per cycle
    merged_away: set[tuple[str, int]] = set()
    for i, (src_a, idx_a, item_a) in enumerate(all_items):
        if (src_a, idx_a) in merged_away:
            continue
        title_a = (item_a.get("title") or item_a.get("name") or "").lower()
        if len(title_a) < 10:
            continue
        for j in range(i + 1, len(all_items)):
            src_b, idx_b, item_b = all_items[j]
            if (src_b, idx_b) in merged_away or src_a == src_b:
                continue
            title_b = (item_b.get("title") or item_b.get("name") or "").lower()
            if len(title_b) < 10:
                continue
            # Token overlap check
            tokens_a = set(re.findall(r"\w{4,}", title_a))
            tokens_b = set(re.findall(r"\w{4,}", title_b))
            if not tokens_a or not tokens_b:
                continue
            overlap = len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))
            if overlap >= 0.6:
                # Merge: keep the one with higher engagement, tag the other
                score_a = item_a.get("score") or item_a.get("stars") or 0
                score_b = item_b.get("score") or item_b.get("stars") or 0
                if score_a >= score_b:
                    item_a.setdefault("also_on", []).append(src_b)
                    merged_away.add((src_b, idx_b))
                else:
                    item_b.setdefault("also_on", []).append(src_a)
                    merged_away.add((src_a, idx_a))

    # Rebuild signals without merged-away items
    deduped: dict[str, list[dict[str, Any]]] = {}
    for source, items in signals.items():
        deduped[source] = [
            item for idx, item in enumerate(items)
            if (source, idx) not in merged_away
        ]

    removed = len(merged_away)
    if removed:
        logger.info(f"Cross-source dedup: merged {removed} duplicate items")
    return deduped


def extract_trending_terms(signals: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Pull concrete searchable terms straight from the scraped signals.

    Strategy:
    - GitHub repo names (e.g. 'open-claw-agents' -> 'open-claw-agents' or just 'open-claw')
    - GitHub repo descriptions for additional product names
    - Distinctive capitalized words from HN/Reddit titles ('Hermes 3', 'Claude Code')
    - Product names from Reddit + HN comments
    - Multi-word product-style phrases (TitleCase or Title Case sequences)
    - YouTube channel/video names and Polymarket question entities
    These become guaranteed reply/like search queries — independent of LLM judgment.
    """
    terms: list[str] = []

    # 1) GitHub repo names — best signal for fresh trending tools
    for repo in signals.get("github", [])[:12]:
        full = repo.get("name", "")
        if "/" not in full:
            continue
        _, name = full.split("/", 1)
        # Convert dashes/underscores to spaces and keep as a 1-3 word search phrase
        cleaned = re.sub(r"[-_]", " ", name).strip()
        # Skip ultra-generic names
        if len(cleaned) < 4 or cleaned.lower() in _STOPWORDS:
            continue
        # Cap at 3 words for X search effectiveness
        words = cleaned.split()
        if len(words) > 3:
            cleaned = " ".join(words[:3])
        if cleaned not in terms:
            terms.append(cleaned)

    # 2) Project/product names from HN + Reddit + Newsletter + YouTube titles
    #    Capture CapitalCased word sequences (e.g. "Claude Code", "Hermes 3", "GPT-OSS")
    title_sources = (
        [s.get("title", "") for s in signals.get("hackernews", [])[:20]]
        + [s.get("title", "") for s in signals.get("reddit", [])[:15]]
        + [s.get("title", "") for s in signals.get("newsletters", [])[:10]]
        + [s.get("title", "") for s in signals.get("youtube", [])[:8]]
    )

    # Also extract from GitHub descriptions for richer product names
    title_sources += [
        r.get("description", "") for r in signals.get("github", [])[:12]
        if r.get("description")
    ]

    cap_re = re.compile(
        r"\b("
        r"(?:[A-Z][a-zA-Z0-9]{2,}(?:[-\s][A-Z][a-zA-Z0-9]+)*"      # CamelCase / Title Case sequences
        r"|[A-Z]{2,}(?:-[A-Z0-9]+)*"                                # All-caps like GPT-OSS, LLM-CLI
        r"|[a-z]+\d+(?:[-\.]\d+)?"                                  # gpt-4, qwen2.5
        r")\b)"
    )
    seen = {t.lower() for t in terms}
    for title in title_sources:
        for m in cap_re.finditer(title):
            tok = m.group(1).strip()
            tok_l = tok.lower()
            if (
                len(tok) < 3
                or tok_l in _STOPWORDS
                or tok_l in seen
                or re.fullmatch(r"\d+", tok)               # pure numbers
            ):
                continue
            seen.add(tok_l)
            terms.append(tok)
            if len(terms) >= 25:
                break
        if len(terms) >= 25:
            break

    # 3) Extract product/entity names from enriched comments (HN + Reddit)
    comment_sources: list[str] = []
    for story in signals.get("hackernews", [])[:8]:
        for c in story.get("top_comments", [])[:3]:
            comment_sources.append(c.get("text", ""))
    for post in signals.get("reddit", [])[:8]:
        for c in post.get("top_comments", [])[:3]:
            comment_sources.append(c.get("text", ""))

    for text in comment_sources:
        for m in cap_re.finditer(text):
            tok = m.group(1).strip()
            tok_l = tok.lower()
            if (
                len(tok) < 3
                or tok_l in _STOPWORDS
                or tok_l in seen
                or re.fullmatch(r"\d+", tok)
            ):
                continue
            seen.add(tok_l)
            terms.append(tok)
            if len(terms) >= 25:
                break
        if len(terms) >= 25:
            break

    # 4) Extract entity names from Polymarket questions
    for market in signals.get("polymarket", [])[:5]:
        question = market.get("question", "")
        for m in cap_re.finditer(question):
            tok = m.group(1).strip()
            tok_l = tok.lower()
            if (
                len(tok) < 3
                or tok_l in _STOPWORDS
                or tok_l in seen
                or re.fullmatch(r"\d+", tok)
            ):
                continue
            seen.add(tok_l)
            terms.append(tok)
            if len(terms) >= 25:
                break

    return terms[:15]


async def fetch_github_recent_hot(client: httpx.AsyncClient, days: int = 7, per_topic: int = 4) -> list[dict[str, Any]]:
    """For each AI topic, fetch recently created repos with the most stars.
    No auth needed; rate-limited to 10 req/min unauth, we stay well under.

    Tighter time window (7d default, was 14d) + randomized topic sample so each
    cycle picks up different freshness slices of the long tail."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    seen: dict[str, dict[str, Any]] = {}
    # Sample 8 of N topics per cycle so we don't redundantly hit all topics every time —
    # adds rotation/variety without sacrificing coverage over a few cycles.
    import random as _random
    sampled_topics = _random.sample(_GITHUB_TOPICS, min(8, len(_GITHUB_TOPICS)))
    for topic in sampled_topics:
        q = f"topic:{topic} created:>{cutoff} stars:>5"
        url = "https://api.github.com/search/repositories"
        params = {"q": q, "sort": "stars", "order": "desc", "per_page": per_topic}
        try:
            r = await client.get(url, params=params, timeout=15.0,
                                 headers={"Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                logger.debug(f"GitHub {topic}: status {r.status_code}")
                continue
            data = r.json()
            for item in data.get("items", []):
                full = item.get("full_name") or ""
                if not full or full in seen:
                    continue
                seen[full] = {
                    "name": full,
                    "description": (item.get("description") or "")[:300],
                    "stars": item.get("stargazers_count", 0),
                    "url": item.get("html_url"),
                    "language": item.get("language"),
                    "topics": item.get("topics", [])[:8],
                    "created_at": item.get("created_at"),
                    "matched_topic": topic,
                }
        except Exception as e:
            logger.debug(f"GitHub fetch failed for {topic}: {e}")

    # Top N by stars across all topics
    top = sorted(seen.values(), key=lambda x: x.get("stars", 0), reverse=True)[:20]
    logger.info(f"GitHub trending: pulled {len(top)} repos across {len(_GITHUB_TOPICS)} topics")
    return top


async def fetch_hackernews_algolia(client: httpx.AsyncClient, niche: str = "AI agents", limit: int = 30) -> list[dict[str, Any]]:
    """Search HN via Algolia API — proper full-text search with date filtering.

    Inspired by last30days-skill's hackernews.py. Replaces the old Firebase
    approach (60+ serial HTTP calls, regex-filtered) with 1-2 Algolia calls.

    Improvements over old approach:
    - Full-text search, not just top-60 title regex matching
    - Date filtering (last 7 days) built into the query
    - optionalWords for flexible multi-token matching
    - Overfetch 2x, then client-side filter by points > 5
    - Comment enrichment for top 3-5 stories
    """
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    overfetch = limit * 2

    # Build search queries — use niche keywords + AI hints
    core = _extract_core_subject(niche)
    search_terms = _flatten_query_for_algolia(core)
    # Broader AI fallback terms to ensure we always find stories
    if len(search_terms.split()) < 2:
        search_terms = "AI agents LLM Claude"

    params = {
        "query": search_terms,
        "tags": "story",
        "numericFilters": f"created_at_i>{cutoff_ts}",
        "hitsPerPage": str(overfetch),
    }
    # Make all-but-first token optional for flexible matching
    tokens = search_terms.split()
    if len(tokens) > 1:
        params["optionalWords"] = " ".join(tokens[1:])

    url = f"https://hn.algolia.com/api/v1/search?{urlencode(params)}"

    try:
        r = await client.get(url, timeout=20.0)
        if r.status_code != 200:
            logger.debug(f"HN Algolia: status {r.status_code}")
            return []
        data = r.json()
    except Exception as e:
        logger.debug(f"HN Algolia search failed: {e}")
        return []

    raw_hits = data.get("hits", [])
    # Client-side quality filter: drop stories with < 5 points
    qualifying = [h for h in raw_hits if (h.get("points") or 0) > 5]
    hits = qualifying[:limit]

    out: list[dict[str, Any]] = []
    for hit in hits:
        story_id = hit.get("objectID") or hit.get("story_id")
        title = hit.get("title") or ""
        if not title:
            continue
        story_url = hit.get("url") or f"https://news.ycombinator.com/item?id={story_id}"
        out.append({
            "title": title,
            "url": story_url,
            "score": hit.get("points", 0),
            "comments": hit.get("num_comments", 0),
            "id": story_id,
            "author": hit.get("author", ""),
            "created_at": hit.get("created_at", ""),
        })

    # Comment enrichment for top 5 stories (fetch actual top comments via Algolia items API)
    enriched = 0
    for story in out[:5]:
        sid = story.get("id")
        if not sid:
            continue
        try:
            cr = await client.get(
                f"https://hn.algolia.com/api/v1/items/{sid}",
                timeout=10.0,
            )
            if cr.status_code != 200:
                continue
            item_data = cr.json()
            children = item_data.get("children", [])
            # Extract top comments by points
            top_comments: list[dict[str, Any]] = []
            for child in children[:20]:  # scan first 20 children
                if child.get("type") != "comment":
                    continue
                comment_text = child.get("text") or ""
                # Strip HTML tags
                comment_text = re.sub(r"<[^>]+>", " ", comment_text).strip()
                comment_text = re.sub(r"\s+", " ", comment_text)[:300]
                if len(comment_text) < 20:
                    continue
                top_comments.append({
                    "text": comment_text,
                    "points": child.get("points") or 0,
                    "author": child.get("author") or "",
                })
            # Sort by points, keep top 5
            top_comments.sort(key=lambda c: c["points"], reverse=True)
            story["top_comments"] = top_comments[:5]
            enriched += 1
        except Exception:
            continue

    dropped = len(raw_hits) - len(qualifying)
    logger.info(
        f"HN Algolia: {len(out)} stories from {len(raw_hits)} raw hits "
        f"(dropped {dropped} low-engagement, enriched {enriched} with comments)"
    )
    return out


_NEWSLETTER_FEEDS = [
    ("AINews",        "https://buttondown.com/ainews/rss"),
    ("Latent Space",  "https://www.latent.space/feed"),
    ("BensBites",     "https://bensbites.beehiiv.com/feed"),
    ("Smol AI",       "https://smol.ai/feed.xml"),
    ("Import AI",     "https://importai.substack.com/feed"),
]


async def fetch_newsletters(client: httpx.AsyncClient, limit: int = 15) -> list[dict[str, Any]]:
    """Pull recent items from curated AI newsletter RSS feeds. Returns flat list ranked by recency."""
    out: list[dict[str, Any]] = []
    for source_name, url in _NEWSLETTER_FEEDS:
        try:
            r = await client.get(url, timeout=10.0, follow_redirects=True,
                                 headers={"User-Agent": "twit-auto/1.0"})
            if r.status_code != 200:
                continue
            # Lightweight parse: pull <item>/<entry> titles + links from XML/Atom without bringing in another dep.
            blocks = re.findall(r"<(item|entry)\b[^>]*>(.*?)</\1>", r.text, flags=re.DOTALL)
            for _, body in blocks[:5]:
                title_m = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.DOTALL)
                link_m  = re.search(r"<link[^>]*?(?:>([^<]+)</link>|href=\"([^\"]+)\")", body)
                if not title_m:
                    continue
                title = re.sub(r"<!\[CDATA\[|\]\]>", "", title_m.group(1)).strip()[:200]
                link = ""
                if link_m:
                    link = (link_m.group(1) or link_m.group(2) or "").strip()
                if not title:
                    continue
                out.append({"source": source_name, "title": title, "url": link})
        except Exception as e:
            logger.debug(f"Newsletter {source_name} failed: {e}")
    logger.info(f"Newsletters: {len(out)} recent items from {len(_NEWSLETTER_FEEDS)} feeds")
    return out[:limit]


async def fetch_reddit_enriched(client: httpx.AsyncClient, niche: str = "AI agents", limit: int = 20) -> list[dict[str, Any]]:
    """Reddit hot posts with dynamic subreddit discovery + comment enrichment.

    Inspired by last30days-skill's reddit.py + reddit_enrich.py:
    - Dynamic subreddit discovery from search results (not just hardcoded)
    - Comment enrichment: fetches actual top comments via Reddit's free JSON API
    - Multi-query expansion: core + review/opinion variants
    - Relevance scoring to suppress off-topic viral content
    """
    out: list[dict[str, Any]] = []
    import random as _random

    # Anchor subreddits that always get checked
    anchor_subs = ["LocalLLaMA", "ChatGPT"]
    # Rotating pool of extra subs for variety
    extra_pool = [
        "singularity", "MachineLearning", "OpenAI", "ArtificialInteligence",
        "LLMDevs", "ClaudeAI", "cursor", "Anthropic", "Oobabooga",
    ]
    extra = _random.sample(extra_pool, min(3, len(extra_pool)))
    subs = anchor_subs + extra

    for sub in subs:
        try:
            r = await client.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=15",
                timeout=10.0,
                headers={"User-Agent": "twit-auto/1.0"},
            )
            if r.status_code != 200:
                continue
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                title = d.get("title", "")
                if not title:
                    continue
                permalink = d.get("permalink", "")
                out.append({
                    "title": title[:200],
                    "url": f"https://reddit.com{permalink}",
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "subreddit": sub,
                    "upvote_ratio": d.get("upvote_ratio", 0),
                    "selftext": (d.get("selftext") or "")[:300],
                    "permalink": permalink,
                })
                if len(out) >= limit * 2:  # overfetch for quality filter
                    break
        except Exception as e:
            logger.debug(f"Reddit {sub} failed: {e}")

    # Relevance scoring — suppress off-topic viral content
    niche_lower = niche.lower()
    for post in out:
        text = f"{post['title']} {post.get('selftext', '')}"
        relevance = token_overlap_relevance(niche_lower, text.lower())
        # AI keyword boost
        if _AI_HINT_RE.search(text):
            relevance = min(1.0, relevance + 0.3)
        post["relevance"] = round(relevance, 2)

    # Sort by combined engagement + relevance, drop very low relevance
    out = [p for p in out if p["relevance"] >= 0.1]
    out.sort(key=lambda p: p["score"] * (0.4 + 0.6 * p["relevance"]), reverse=True)
    out = out[:limit]

    # Comment enrichment for top 5 posts — get actual community discussion
    enriched = 0
    for post in out[:5]:
        permalink = post.get("permalink", "")
        if not permalink:
            continue
        try:
            cr = await client.get(
                f"https://www.reddit.com{permalink}.json?limit=10",
                timeout=10.0,
                headers={"User-Agent": "twit-auto/1.0"},
            )
            if cr.status_code != 200:
                continue
            json_data = cr.json()
            if not isinstance(json_data, list) or len(json_data) < 2:
                continue
            comments_listing = json_data[1].get("data", {}).get("children", [])
            top_comments: list[dict[str, Any]] = []
            for c in comments_listing[:10]:
                cd = c.get("data", {})
                body = (cd.get("body") or "")[:300]
                if len(body) < 20 or cd.get("stickied"):
                    continue
                top_comments.append({
                    "text": body,
                    "score": cd.get("score", 0),
                    "author": cd.get("author", ""),
                })
            top_comments.sort(key=lambda c: c["score"], reverse=True)
            post["top_comments"] = top_comments[:5]
            enriched += 1
        except Exception:
            continue

    logger.info(f"Reddit: {len(out)} posts from {len(subs)} subs (enriched {enriched} with comments)")
    return out


# ---------------------------------------------------------------------------
# New signal sources (inspired by last30days-skill)
# ---------------------------------------------------------------------------

def _jsonish_list(value: Any) -> list[Any]:
    """Return a list from API fields that may already be lists or JSON strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _extract_yes_probability(market: dict[str, Any]) -> float | None:
    """Extract the Yes-side probability from a Polymarket market object."""
    prices = _jsonish_list(market.get("outcomePrices"))
    if not prices:
        return None

    outcomes = _jsonish_list(market.get("outcomes"))
    yes_idx = 0
    for idx, outcome in enumerate(outcomes):
        if str(outcome).strip().lower() == "yes":
            yes_idx = idx
            break

    probability = _coerce_float(prices[yes_idx]) if yes_idx < len(prices) else None
    if probability is None:
        probability = _coerce_float(prices[0])
    if probability is None:
        return None
    return max(0.0, min(1.0, probability))


def _format_probability(value: Any) -> str:
    probability = _coerce_float(value)
    if probability is None:
        return ""
    return f" ({int(probability * 100)}% Yes)"


def _format_dollar_volume(value: Any) -> str:
    volume = _coerce_float(value)
    if not volume:
        return ""
    return f"${int(volume):,} volume"


async def fetch_polymarket_ai(client: httpx.AsyncClient, limit: int = 10) -> list[dict[str, Any]]:
    """Fetch AI-related prediction markets from Polymarket.

    Inspired by last30days-skill's polymarket.py. Free API, no auth required.
    Returns prediction market data for AI/tech topics — powerful signal for
    what the crowd is betting on. Each market has real money behind it.
    """
    out: list[dict[str, Any]] = []
    try:
        # Use /events, not /markets: the `tag=ai-tech` param is silently ignored
        # (returns politics) and /markets' top page carries no AI questions, while
        # /events does. Filter with the shared word-boundary AI regex — plain
        # substring matching false-positives on "T(ai)wan" / "R(ai)mondo".
        r = await client.get(
            "https://gamma-api.polymarket.com/events",
            params={"limit": 100, "active": "true", "closed": "false"},
            timeout=10.0,
        )
        events = r.json() if r.status_code == 200 else []
        if not isinstance(events, list):
            events = []
        for ev in events:
            title = ev.get("title") or ""
            if not title or not _AI_HINT_RE.search(title):
                continue
            nested = ev.get("markets") or []
            out.append({
                "question": title[:200],
                "probability": _extract_yes_probability(nested[0]) if nested else None,
                "volume": ev.get("volume") or 0,
                "url": f"https://polymarket.com/event/{ev.get('slug', '')}",
                "end_date": ev.get("endDate") or "",
            })
    except Exception as e:
        logger.debug(f"Polymarket fetch failed: {e}")

    # Sort by volume (most money = strongest signal)
    out.sort(key=lambda m: _coerce_float(m.get("volume")) or 0, reverse=True)
    out = out[:limit]
    logger.info(f"Polymarket: {len(out)} AI-relevant prediction markets")
    return out


async def fetch_youtube_trending(client: httpx.AsyncClient, niche: str = "AI agents", limit: int = 10) -> list[dict[str, Any]]:
    """Fetch trending AI videos from YouTube Data API.

    Optional — only activates if YOUTUBE_API_KEY is set in environment.
    Returns recent AI/tech videos with engagement metrics.
    Falls back gracefully to empty list if no API key.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        return []  # Graceful no-op

    core = _extract_core_subject(niche)
    out: list[dict[str, Any]] = []

    try:
        r = await client.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": core,
                "type": "video",
                "order": "date",
                "publishedAfter": (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "maxResults": str(limit * 2),
                "key": api_key,
            },
            timeout=15.0,
        )
        if r.status_code != 200:
            logger.debug(f"YouTube API: status {r.status_code}")
            return []

        items = r.json().get("items", [])
        video_ids = [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

        # Fetch video stats in batch
        stats = {}
        if video_ids:
            sr = await client.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "statistics",
                    "id": ",".join(video_ids[:limit]),
                    "key": api_key,
                },
                timeout=15.0,
            )
            if sr.status_code == 200:
                for v in sr.json().get("items", []):
                    s = v.get("statistics", {})
                    stats[v["id"]] = {
                        "views": int(s.get("viewCount", 0)),
                        "likes": int(s.get("likeCount", 0)),
                    }

        for item in items[:limit]:
            vid = item.get("id", {}).get("videoId")
            if not vid:
                continue
            snippet = item.get("snippet", {})
            vid_stats = stats.get(vid, {})
            out.append({
                "title": snippet.get("title", "")[:200],
                "channel": snippet.get("channelTitle", ""),
                "url": f"https://youtube.com/watch?v={vid}",
                "views": vid_stats.get("views", 0),
                "likes": vid_stats.get("likes", 0),
                "published_at": snippet.get("publishedAt", ""),
            })

        # Sort by views
        out.sort(key=lambda v: v.get("views", 0), reverse=True)
    except Exception as e:
        logger.debug(f"YouTube fetch failed: {e}")

    logger.info(f"YouTube: {len(out)} trending AI videos")
    return out


# ---------------------------------------------------------------------------
# Strategy synthesis
# ---------------------------------------------------------------------------

STRATEGY_SYSTEM = (
    "You are the strategy brain of an AI/tech-focused X account. You research what's "
    "actually being built and discussed right now, then decide what searches the bot "
    "should run this cycle to find conversations worth joining and topics worth posting about. "
    "You output STRICT JSON only — no preamble, no markdown, no code fence."
)


def _build_strategy_prompt(
    state: dict[str, Any],
    signals: dict[str, list[dict[str, Any]]],
    trending_terms: list[str],
) -> str:
    niche = state.get("_niche", "AI agents and automation")
    memory = state.get("search_memory", {})
    recent_queries = memory.get("queries_run", [])[-30:]
    topics_seen = memory.get("topics_seen", [])[-50:]
    repos_tracked = memory.get("github_repos_tracked", [])[-30:]
    queued = memory.get("trends_to_explore_later", [])

    # Compact signal summaries
    gh = "\n".join(
        f"  - {r['name']} ({r['stars']}★, {r.get('language','?')}): {r.get('description','')[:140]}"
        for r in signals.get("github", [])[:15]
    )

    # HN stories with comment insights
    hn_lines: list[str] = []
    for s in signals.get("hackernews", [])[:12]:
        line = f"  - [{s['score']} pts, {s.get('comments', 0)} comments] {s['title']}"
        top_comments = s.get("top_comments", [])
        if top_comments:
            best = top_comments[0]
            line += f"\n    💬 Top comment ({best.get('points', 0)} pts): \"{best['text'][:120]}...\""
        hn_lines.append(line)
    hn = "\n".join(hn_lines)

    # Reddit posts with comment insights and engagement quality
    rd_lines: list[str] = []
    for s in signals.get("reddit", [])[:10]:
        ratio = s.get("upvote_ratio", 0)
        ratio_str = f", {int(ratio * 100)}% upvoted" if ratio else ""
        line = f"  - [r/{s['subreddit']} {s['score']} pts{ratio_str}] {s['title']}"
        top_comments = s.get("top_comments", [])
        if top_comments:
            best = top_comments[0]
            line += f"\n    💬 Top comment ({best.get('score', 0)} pts): \"{best['text'][:120]}...\""
        rd_lines.append(line)
    rd = "\n".join(rd_lines)

    nl = "\n".join(
        f"  - [{s['source']}] {s['title']}"
        for s in signals.get("newsletters", [])[:10]
    )

    # Polymarket prediction markets
    pm_lines: list[str] = []
    for m in signals.get("polymarket", [])[:8]:
        prob_str = _format_probability(m.get("probability"))
        vol_str = _format_dollar_volume(m.get("volume"))
        pm_lines.append(f"  - {m['question']}{prob_str} [{vol_str}]")
    pm = "\n".join(pm_lines)

    # YouTube trending (optional)
    yt_lines: list[str] = []
    for v in signals.get("youtube", [])[:6]:
        views = v.get("views", 0)
        views_str = f"{views:,} views" if views else ""
        yt_lines.append(f"  - [{v.get('channel', '')}] {v['title']} ({views_str})")
    yt = "\n".join(yt_lines)

    # Community sentiment summary (synthesized from comments across sources)
    sentiment_lines: list[str] = []
    for s in signals.get("hackernews", [])[:5]:
        if s.get("top_comments"):
            sentiment_lines.append(
                f"  HN on '{s['title'][:60]}': "
                f"{len(s['top_comments'])} comments analyzed, "
                f"top insight: \"{s['top_comments'][0]['text'][:100]}...\""
            )
    for s in signals.get("reddit", [])[:5]:
        if s.get("top_comments"):
            sentiment_lines.append(
                f"  Reddit r/{s['subreddit']} on '{s['title'][:50]}': "
                f"{len(s['top_comments'])} comments, "
                f"sentiment: \"{s['top_comments'][0]['text'][:100]}...\""
            )
    sentiment = "\n".join(sentiment_lines[:8])

    trending_block = "\n".join(f"  - {t}" for t in trending_terms) or "  (none extracted)"

    return f"""NICHE: {niche}

LIVE SIGNAL — GitHub repos (recently created, sorted by stars):
{gh or "  (none)"}

LIVE SIGNAL — HackerNews AI stories (Algolia search, last 7 days, with top comments):
{hn or "  (none)"}

LIVE SIGNAL — Reddit hot posts (with comment insights + upvote quality):
{rd or "  (none)"}

LIVE SIGNAL — Recent AI newsletters (AINews, Latent Space, BensBites, Smol AI, Import AI):
{nl or "  (none)"}

LIVE SIGNAL — Polymarket AI prediction markets (real money, real odds):
{pm or "  (none — no AI markets active)"}

LIVE SIGNAL — YouTube trending AI content:
{yt or "  (none — YOUTUBE_API_KEY not set or no results)"}

COMMUNITY SENTIMENT — What developers and users are actually saying (from comments):
{sentiment or "  (no comment data available this cycle)"}

DETERMINISTICALLY EXTRACTED TRENDING TERMS (product names, repo names, projects
mentioned across the signals — these are FRESH and SEARCHABLE on X right now):
{trending_block}

MEMORY — recent search queries this bot has run (don't repeat unless still very fresh):
{json.dumps(recent_queries[-15:], default=str)}

MEMORY — topics already covered:
{json.dumps(topics_seen[-25:])}

MEMORY — GitHub repos already tweeted about (skip these):
{json.dumps([r.get("name") for r in repos_tracked])}

MEMORY — trends queued for future exploration:
{json.dumps(queued[-15:])}

TASK
Output a JSON object with this exact shape:

{{
  "reply_queries": [
    "5-7 short search queries (1-3 words each) for finding LIVE tweets to reply to.",
    "REQUIRED: AT LEAST 3 of these queries must come directly from the TRENDING TERMS or LIVE SIGNALS above — use the actual names of trending repos, products, or projects.",
    "Examples of GOOD queries derived from signals: the repo name without owner, a product name from HN, a project from Reddit.",
    "Then 2-3 broader niche queries (RAG, AI agents, LLM tools) for variety."
  ],
  "follow_queries": [
    "2-3 search queries for finding accounts worth following.",
    "Should be specific roles: 'AI agents founder', 'building Claude tools', 'n8n developer'."
  ],
  "like_queries": [
    "3-4 broad queries for finding tweets worth liking. Should always have lots of live results.",
    "Examples: 'AI agents', 'LLM', 'Claude', 'Cursor'."
  ],
  "tweet_topics": [
    {{
      "angle": "A concrete tweet idea pulled from one of the LIVE SIGNALS above.",
      "context": "What's interesting about it and what a builder should take from it.",
      "source_url": "The actual URL from the signals above. Do not invent."
    }}
  ],
  "github_repos_to_mention": [
    {{
      "name": "owner/repo from the GitHub signal above ONLY",
      "why": "One sentence on why it's interesting",
      "url": "the actual URL"
    }}
  ],
  "memory_updates": {{
    "topics_seen_add": ["new topics this cycle touched on"],
    "trends_to_explore_later": ["specific things worth digging into next cycle"]
  }}
}}

RULES
- Only include GitHub repos from the GitHub signal above. Do NOT invent repo names.
- Tweet topics MUST cite a real URL from the signals. No hallucinated sources.
- reply_queries should be CURRENT — favor specifically-named tools/projects/people over generic terms.
- Use the COMMUNITY SENTIMENT data to pick the most discussion-worthy angles for tweets.
- If Polymarket has active AI predictions, reference those odds in tweet ideas — they're grounded in real money.
- Avoid queries the bot ran in the last few cycles unless the topic is still red-hot.
- If signals are weak, fall back to broad evergreen niche queries.

CRITICAL OUTPUT FORMAT
- Output valid RFC 8259 JSON.
- No prose, no preamble, no code fences (```), no comments (// or /* */), no trailing commas.
- Use straight ASCII double quotes only, never curly quotes.
- Start with {{ and end with }}. Nothing else before or after."""


def _extract_json(text: str) -> dict[str, Any] | None:
    """3-pass JSON extraction for messy LLM output.

    Pass 1 — stdlib lenient (strict=False, handles control chars in strings).
    Pass 2 — manual cleanup (strip fences/comments/trailing commas/smart quotes).
    Pass 3 — json-repair library (fixes missing commas, unbalanced brackets,
             unescaped quotes inside strings, truncation, etc.).
    """
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        # Maybe truncated — still try repair on what we have
        blob = text
    else:
        blob = text[start:end + 1]

    # Pass 1: stdlib lenient
    try:
        return json.loads(blob, strict=False)
    except Exception:
        pass

    # Pass 2: manual cleanup
    cleaned = blob
    cleaned = re.sub(r"//[^\n\r]*", "", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    # Pass 3: json-repair (handles missing commas, unbalanced brackets, etc.)
    try:
        import json_repair
        result = json_repair.loads(cleaned)
        if isinstance(result, dict) and result:
            logger.info("Strategy JSON recovered via json-repair (pass 3).")
            return result
    except Exception as e:
        logger.warning(f"Strategy JSON unrecoverable: {e}")
        logger.debug(f"JSON snippet: {cleaned[:300]}")

    return None


def _default_strategy() -> dict[str, Any]:
    """Fallback when LLM strategy fails. Broad evergreen queries that always have live results."""
    return {
        "reply_queries": ["AI agents", "Claude AI", "Cursor", "LLM", "RAG", "AI tools", "n8n"],
        "follow_queries": ["AI agents founder", "Claude developer", "indie hacker AI"],
        "like_queries": ["AI agents", "Claude", "LLM", "AI tools"],
        "tweet_topics": [],
        "github_repos_to_mention": [],
        "memory_updates": {"topics_seen_add": [], "trends_to_explore_later": []},
    }


async def synthesize_strategy(
    state: dict[str, Any],
    niche: str,
    llm_call: Callable[[str, str], Awaitable[str | None]],
) -> dict[str, Any]:
    """Top-level entrypoint. Pulls signals from 6 sources in parallel,
    calls the LLM, returns a strategy dict.
    Falls back to a safe default on any failure.

    Sources fetched in parallel via asyncio.gather:
    1. GitHub trending repos
    2. HackerNews via Algolia (with comment enrichment)
    3. Reddit with comment enrichment
    4. AI newsletter RSS feeds
    5. Polymarket prediction markets
    6. YouTube trending (optional, needs YOUTUBE_API_KEY)
    """
    state["_niche"] = niche  # injected for prompt building

    async with httpx.AsyncClient() as client:
        # Parallel signal fetching — all sources at once (~5-8s vs ~15-20s sequential)
        results = await asyncio.gather(
            fetch_github_recent_hot(client),
            fetch_hackernews_algolia(client, niche=niche),
            fetch_reddit_enriched(client, niche=niche),
            fetch_newsletters(client),
            fetch_polymarket_ai(client),
            fetch_youtube_trending(client, niche=niche),
            return_exceptions=True,
        )

    # Unpack results, replacing exceptions with empty lists
    def _safe(result: Any) -> list[dict[str, Any]]:
        if isinstance(result, Exception):
            logger.warning(f"Signal fetch failed: {type(result).__name__}: {result}")
            return []
        return result if isinstance(result, list) else []

    gh, hn, rd, nl, pm, yt = [_safe(r) for r in results]

    signals: dict[str, list[dict[str, Any]]] = {
        "github": gh,
        "hackernews": hn,
        "reddit": rd,
        "newsletters": nl,
        "polymarket": pm,
        "youtube": yt,
    }

    # Cross-source deduplication — merge duplicate stories across sources
    signals = _deduplicate_cross_source(signals)

    # Log signal summary
    total = sum(len(v) for v in signals.values())
    logger.info(
        f"Signals collected: {total} total — "
        f"GH={len(signals['github'])}, HN={len(signals['hackernews'])}, "
        f"Reddit={len(signals['reddit'])}, NL={len(signals['newsletters'])}, "
        f"PM={len(signals['polymarket'])}, YT={len(signals['youtube'])}"
    )

    # Deterministic trending-term extraction — guaranteed real, signal-derived queries
    trending_terms_raw = extract_trending_terms(signals)
    logger.info(f"Extracted {len(trending_terms_raw)} trending terms: {trending_terms_raw[:8]}")

    # Niche filter — drop crypto/memecoin/off-topic noise before injection
    trending_terms = await filter_terms_by_niche(trending_terms_raw, state.get("_niche", ""), llm_call)
    if len(trending_terms) < len(trending_terms_raw):
        logger.info(
            f"Niche filter: {len(trending_terms_raw)} -> {len(trending_terms)} terms "
            f"(kept: {trending_terms[:8]})"
        )

    prompt = _build_strategy_prompt(state, signals, trending_terms)
    raw = await llm_call(prompt, STRATEGY_SYSTEM)
    parsed = _extract_json(raw or "")
    if not parsed:
        logger.warning("Strategy LLM call failed or unparseable — using default strategy.")
        strategy = _default_strategy()
    else:
        strategy = _validate_strategy(parsed, signals)

    # Force-inject the deterministically extracted trending terms.
    # Suppress terms the bot has used in the last 12 hours so search rotates instead
    # of hammering the same handful of trending names every cycle.
    if trending_terms:
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
        recently_used: set[str] = set()
        for entry in (state.get("search_memory", {}).get("queries_run") or [])[-60:]:
            try:
                ts = datetime.fromisoformat((entry.get("ts") or "").replace("Z", "+00:00"))
                if ts >= recent_cutoff:
                    recently_used.add((entry.get("query") or "").strip().lower())
            except Exception:
                continue

        # Prefer terms NOT recently used; fall back to recently-used only if we'd have nothing left
        fresh_terms = [t for t in trending_terms if t.lower() not in recently_used]
        stale_terms = [t for t in trending_terms if t.lower() in recently_used]
        # Always inject some fresh; if pool is thin, allow a couple of stale at the end
        ordered_pool = fresh_terms + stale_terms
        if recently_used and fresh_terms:
            logger.info(
                f"Trending-term rotation: {len(fresh_terms)} fresh, "
                f"{len(stale_terms)} recently used (suppressing stale)"
            )

        # Reply queries: prepend top 4 (preferring fresh)
        forced = ordered_pool[:4]
        existing_lower = {q.lower() for q in strategy["reply_queries"]}
        for term in reversed(forced):
            if term.lower() not in existing_lower:
                strategy["reply_queries"].insert(0, term)
                existing_lower.add(term.lower())
        strategy["reply_queries"] = strategy["reply_queries"][:10]

        # Like queries: top 3 (preferring fresh)
        like_forced = ordered_pool[:3]
        existing_lower = {q.lower() for q in strategy["like_queries"]}
        for term in reversed(like_forced):
            if term.lower() not in existing_lower:
                strategy["like_queries"].insert(0, term)
                existing_lower.add(term.lower())
        strategy["like_queries"] = strategy["like_queries"][:6]

    strategy["_signals"] = signals
    strategy["_trending_terms"] = trending_terms
    return strategy


# ---------------------------------------------------------------------------
# Niche filter for trending terms
# ---------------------------------------------------------------------------

_NICHE_FILTER_SYSTEM = (
    "You filter a list of trending terms to only those that fit a specific niche. "
    "You err on the side of keeping ambiguous terms (could be on-niche) and only "
    "drop terms that are clearly off-niche. You output STRICT JSON only."
)


async def filter_terms_by_niche(
    terms: list[str],
    niche: str,
    llm_call: Callable[[str, str], Awaitable[str | None]],
) -> list[str]:
    """Filter trending terms to only those on-niche.
    Returns the subset (in original order) that's relevant.
    On LLM failure, returns the original list unchanged (don't lose data)."""
    if not terms:
        return []

    numbered = "\n".join(f"  [{i}] {t}" for i, t in enumerate(terms))
    prompt = f"""NICHE: {niche}

CANDIDATE TRENDING TERMS:
{numbered}

For each term, decide keep vs drop.

ALWAYS DROP if the term contains or relates to:
- crypto, memecoin, token, ico, presale, "pump", airdrop, wallet exploit
- polymarket, prediction market, sports betting, gambling, casino
- forex / day trading / signal group / "to the moon"
- politics, NSFW, religion, drama, celebrity gossip

ALWAYS KEEP if the term is:
- an unfamiliar-looking single word or repo-style name (foo, bar, qux-agents) — these are
  usually new tools / libraries / projects. When in doubt, KEEP. Better to over-include than miss
  the next hot agent framework.
- mentions: ai, llm, agent, gpt, claude, gemini, rag, mcp, embedding, vector,
  langchain, n8n, cursor, claude code, anthropic, openai, hugging face, transformer

For each dropped term, give a one-word reason from this list:
crypto · gambling · politics · nsfw · drama · sports · forex · spam · other

Return JSON only:
{{
  "keep": [<list of int indices to keep>],
  "drop_reasons": {{"<idx>": "<one-word reason>"}}
}}"""
    raw = await llm_call(prompt, _NICHE_FILTER_SYSTEM)
    parsed = _extract_json(raw or "")
    if not parsed:
        logger.warning("Niche filter LLM failed — keeping all trending terms.")
        return terms

    keep_indices = parsed.get("keep") or []
    try:
        keep_set = {int(i) for i in keep_indices if isinstance(i, (int, str)) and str(i).strip().lstrip("-").isdigit()}
    except Exception:
        return terms

    filtered = [t for i, t in enumerate(terms) if i in keep_set]
    drop_reasons = parsed.get("drop_reasons") or {}
    dropped = [(terms[int(i)], reason) for i, reason in drop_reasons.items()
               if str(i).isdigit() and int(i) < len(terms)]
    if dropped:
        logger.info(f"Niche filter dropped: {dropped[:5]}")

    # Safety net: if filter killed EVERYTHING, that's probably a bug — keep all
    if not filtered and terms:
        logger.warning("Niche filter dropped all terms — falling back to unfiltered.")
        return terms

    return filtered


# ---------------------------------------------------------------------------
# Pre-flight tweet critic
# ---------------------------------------------------------------------------

_CRITIC_SYSTEM = (
    "You are a brutally honest X growth coach. You rate tweets/replies on whether "
    "they'd actually drive engagement. You hate generic LinkedIn-style writing. "
    "You output STRICT JSON only — no markdown, no preamble."
)

# Terms commonly muted by AI/tech-Twitter users. X's `muted_keyword_filter` hides
# any tweet containing a viewer's muted word — so if our draft contains these,
# we're invisible to a meaningful slice of our target audience.
# Source: X algorithm repo + observed muting patterns in dev/AI circles.
COMMONLY_MUTED_TERMS = [
    # Crypto / web3 / financial speculation
    "web3", "nft", "crypto", "blockchain", "$btc", "$eth", "memecoin", "shitcoin",
    "polymarket", "pumpfun", "rugpull", "to the moon", "wagmi", "ngmi",
    # AI hype phrases people mute en masse
    "agi achieved", "we're so back", "it's over", "agi internally", "this changes everything",
    "game changer", "10x engineer", "vibe shift",
    # Political / divisive (we want to be apolitical for max reach)
    "trump", "biden", "election", "maga", "woke", "liberal", "conservative",
    # Generic LinkedIn slop most people mute
    "thoughts?", "hot take", "unpopular opinion", "let that sink in",
    "ratio", "this is huge", "absolutely massive", "🚨",
]


def find_muted_terms(text: str) -> list[str]:
    """Return any commonly-muted terms found in the draft (case-insensitive substring)."""
    t = text.lower()
    return [term for term in COMMONLY_MUTED_TERMS if term in t]


async def critique_text(
    text: str,
    role: str,                # "tweet" | "reply" | "quote"
    niche: str,
    style_notes: str,
    llm_call: Callable[[str, str], Awaitable[str | None]],
) -> dict[str, Any]:
    """Rate a draft 1-10 across multiple dimensions. Returns:
        {score: int, hook: int, voice_match: int, value: int, issues: [str], verdict: str}
    """
    first_line = (text.split("\n", 1)[0] or "")[:80]
    prompt = f"""NICHE: {niche}

VOICE THIS ACCOUNT SHOULD HAVE:
{style_notes[:1200]}

DRAFT {role.upper()}:
\"\"\"
{text}
\"\"\"

FIRST 80 CHARS (this is what determines whether someone scrolls past or stops):
{first_line}

Rate this draft on 1-10 scales:
- hook: how strong is the opening as a whole?
- first_line_hook: would the FIRST LINE alone stop a thumb mid-scroll? P(not_dwelled) is a heavy negative weight in X's algorithm — if line 1 doesn't grab, the tweet is invisible. (cap overall score at 6 if first_line_hook < 7)
- voice_match: does this sound like the niche/voice above, or generic AI slop?
- value: does it actually say something interesting?
- grounding: is every claim supported, with concrete names / a source link? (cap overall score at 6 if grounding < 7)

PREDICTED ENGAGEMENT — rate each on 1-10 how likely this tweet is to earn the signal
(these are the actual weighted signals in X's Phoenix ranker):
- p_favorite: how like-worthy?
- p_reply: does it invite a response, contrarian pushback, or fill-in-the-blank?
- p_quote: would someone quote-tweet this to add their own take?
- p_share_dm: would a reader DM this to a specific friend? (highest-value signal — save-worthy content)
- p_profile_click: does it make readers curious about who wrote it?
- p_dwell: does it have enough substance to make someone stop and read?

CRITICAL GROUNDING CHECKS — auto-flag and lower the score:
- Mentions a product/model/repo without a URL or clear source -> flag "missing source link, ambiguous reference"
- Sounds like an announcement of an official release when the source is a community repo or HN post -> flag "presents a side-project as an official launch"
- States specific numbers (parameter counts, benchmarks, dates, version) that aren't obviously sourced -> flag "unverifiable specific claim"
- A name that sounds like an Anthropic/OpenAI/Google product but is actually a third-party repo (e.g. 'Claude Mythos', 'GPT-OSS-Studio') -> flag "ambiguous name, must clarify it's a community project"

Then give an overall score (1-10). 7+ = post it. Under 7 = regenerate.

List specific issues (banned words, weak hook, generic phrasing, LinkedIn energy, hashtag spam, MISSING SOURCE LINK, AMBIGUOUS PRODUCT NAME, etc.).

Return JSON only:
{{
  "hook": <int 1-10>,
  "first_line_hook": <int 1-10>,
  "voice_match": <int 1-10>,
  "value": <int 1-10>,
  "grounding": <int 1-10>,
  "p_favorite": <int 1-10>,
  "p_reply": <int 1-10>,
  "p_quote": <int 1-10>,
  "p_share_dm": <int 1-10>,
  "p_profile_click": <int 1-10>,
  "p_dwell": <int 1-10>,
  "score": <int 1-10>,
  "issues": ["specific problem 1", "specific problem 2"],
  "verdict": "post" or "regenerate"
}}"""
    raw = await llm_call(prompt, _CRITIC_SYSTEM)
    parsed = _extract_json(raw or "")
    if not parsed:
        # Conservative fallback — let it through but log
        return {"score": 7, "hook": 7, "voice_match": 7, "value": 7, "issues": [], "verdict": "post"}
    # Coerce types defensively
    try:
        score = int(parsed.get("score", 7))
    except Exception:
        score = 7
    grounding = int(parsed.get("grounding", 7) or 7)
    first_line_hook = int(parsed.get("first_line_hook", 7) or 7)
    # Only enforce grounding/hook caps on tweet-class content. Replies and follow-ups
    # are conversational short-form and shouldn't be held to source-URL standards.
    is_tweet_class = role in ("tweet", "quote")
    if is_tweet_class:
        if grounding < 7:
            score = min(score, 6)
        if first_line_hook < 7:
            score = min(score, 6)

    # Muted-keyword hard cap (X algorithm muted_keyword_filter) — applies universally,
    # we never want our content invisible to anyone who's muted these terms.
    muted_hits = find_muted_terms(text)
    issues = list(parsed.get("issues") or [])
    if muted_hits:
        score = min(score, 5)  # forces regenerate
        issues.append(f"contains commonly-muted terms: {', '.join(muted_hits)}")

    # Predicted-engagement composite — weighted sum approximating Phoenix scorer
    p_fav   = int(parsed.get("p_favorite", 6) or 6)
    p_rep   = int(parsed.get("p_reply", 6) or 6)
    p_quote = int(parsed.get("p_quote", 6) or 6)
    p_dm    = int(parsed.get("p_share_dm", 6) or 6)
    p_prof  = int(parsed.get("p_profile_click", 6) or 6)
    p_dwell = int(parsed.get("p_dwell", 6) or 6)
    weighted = (p_dm * 5 + p_quote * 4 + p_rep * 3 + p_prof * 2 + p_fav * 1 + p_dwell * 1) / 16
    predicted_engagement = round(weighted, 2)
    # Only gate on predicted engagement for tweet-class. Replies don't need to be
    # save-worthy or DM-shareable — they need to be context-appropriate.
    if is_tweet_class and predicted_engagement < 6.0:
        score = min(score, 6)
        issues.append(f"low predicted engagement ({predicted_engagement}/10)")

    return {
        "score": max(1, min(10, score)),
        "hook": int(parsed.get("hook", 7) or 7),
        "first_line_hook": max(1, min(10, first_line_hook)),
        "voice_match": int(parsed.get("voice_match", 7) or 7),
        "value": int(parsed.get("value", 7) or 7),
        "grounding": max(1, min(10, grounding)),
        "p_favorite": p_fav, "p_reply": p_rep, "p_quote": p_quote,
        "p_share_dm": p_dm, "p_profile_click": p_prof, "p_dwell": p_dwell,
        "predicted_engagement": predicted_engagement,
        "muted_terms": muted_hits,
        "issues": issues,
        "verdict": parsed.get("verdict") or ("post" if score >= 7 else "regenerate"),
    }


# ---------------------------------------------------------------------------
# Smart reply candidate analyzer (features 2 + 8 + 9 combined)
# ---------------------------------------------------------------------------

_REPLY_ANALYZER_SYSTEM = (
    "You analyze candidate tweets to find the BEST one to reply to for growing a "
    "specific niche. You ruthlessly filter out spam, giveaways, ragebait, off-topic, "
    "and low-quality posts. You output STRICT JSON only."
)


async def analyze_reply_candidates(
    candidates: list[dict[str, Any]],
    niche: str,
    llm_call: Callable[[str, str], Awaitable[str | None]],
) -> dict[str, Any] | None:
    """Given a list of candidate tweets, classify each (spam/giveaway/ragebait/genuine)
    + sentiment + reply-worthiness, return the best one to reply to plus its classification.

    Each candidate: {idx, text, likes, age_minutes}
    Returns: {best_idx: int, classification: str, sentiment: str, reply_style: str, all: [...]}
    Or None if no candidate is reply-worthy."""
    if not candidates:
        return None

    listing = "\n".join(
        f"[{c['idx']}] (likes={c.get('likes',0)}, age={c.get('age_minutes','?')}min) {c.get('text','')[:300]}"
        for c in candidates
    )

    prompt = f"""NICHE: {niche}

Candidate tweets to potentially reply to:

{listing}

For each, classify:
- type: one of [spam, giveaway, ragebait, off_topic, genuine]
- sentiment: one of [announcement, question, opinion, complaint, hot_take, technical_problem, neutral]
- reply_worthiness: int 1-10 (would a reply genuinely add value AND get noticed?)
- skip: true if type is spam/giveaway/ragebait/off_topic OR worthiness < 5

Then pick the BEST candidate to reply to (highest worthiness, NOT skipped).
If ALL candidates should be skipped, set best_idx to null.

Return JSON only:
{{
  "best_idx": <int or null>,
  "reply_style": "<one of: ask_followup_question | offer_specific_insight | gentle_pushback | share_related_experience>",
  "all": [
    {{"idx": <int>, "type": "<>", "sentiment": "<>", "reply_worthiness": <int>, "skip": <bool>, "skip_reason": "<short reason or null>"}}
  ]
}}"""
    raw = await llm_call(prompt, _REPLY_ANALYZER_SYSTEM)
    parsed = _extract_json(raw or "")
    if not parsed:
        # Fallback: pick first non-empty candidate
        if candidates:
            return {
                "best_idx": candidates[0]["idx"],
                "reply_style": "offer_specific_insight",
                "all": [],
            }
        return None
    best_idx = parsed.get("best_idx")
    if best_idx is None:
        return None
    return {
        "best_idx": int(best_idx),
        "reply_style": parsed.get("reply_style") or "offer_specific_insight",
        "all": parsed.get("all") or [],
    }


def _validate_strategy(s: dict[str, Any], signals: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Clean and validate the LLM-produced strategy. Drops invented URLs/repos."""
    out = _default_strategy()

    def _slist(v, n=10):
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if isinstance(x, (str, int)) and str(x).strip()][:n]

    out["reply_queries"]  = _slist(s.get("reply_queries"), 8) or out["reply_queries"]
    out["follow_queries"] = _slist(s.get("follow_queries"), 5) or out["follow_queries"]
    out["like_queries"]   = _slist(s.get("like_queries"), 6) or out["like_queries"]

    # Only accept repos that exist in our GitHub signal
    valid_repos = {r["name"] for r in signals.get("github", [])}
    repos_out = []
    for r in s.get("github_repos_to_mention") or []:
        if not isinstance(r, dict):
            continue
        name = (r.get("name") or "").strip()
        if name in valid_repos:
            # Pull canonical url/stars from signal, not from LLM
            canonical = next((g for g in signals["github"] if g["name"] == name), None)
            if canonical:
                repos_out.append({
                    "name": name,
                    "why": (r.get("why") or "")[:300],
                    "url": canonical["url"],
                    "stars": canonical["stars"],
                    "description": canonical.get("description", ""),
                })
    out["github_repos_to_mention"] = repos_out[:5]

    # Tweet topics must reference a real source_url from signals
    valid_urls = {g["url"] for g in signals.get("github", [])} | \
                 {h["url"] for h in signals.get("hackernews", [])} | \
                 {r["url"] for r in signals.get("reddit", [])} | \
                 {n["url"] for n in signals.get("newsletters", []) if n.get("url")}
    topics_out = []
    for t in s.get("tweet_topics") or []:
        if not isinstance(t, dict):
            continue
        url = (t.get("source_url") or "").strip()
        if url and url in valid_urls:
            topics_out.append({
                "angle": (t.get("angle") or "")[:500],
                "context": (t.get("context") or "")[:500],
                "source_url": url,
            })
    out["tweet_topics"] = topics_out[:5]

    mu = s.get("memory_updates") or {}
    out["memory_updates"] = {
        "topics_seen_add": _slist(mu.get("topics_seen_add"), 20),
        "trends_to_explore_later": _slist(mu.get("trends_to_explore_later"), 20),
    }

    return out
