"""
Trend discovery + strategy synthesis.

Replaces hardcoded REPLY_SEARCH_QUERIES / news pipelines with an LLM-driven layer:
1. Fetches raw signals from GitHub, HackerNews, Reddit.
2. Hands the signals + bot memory to an LLM.
3. Receives a structured strategy: what to search, what to reply to, what to tweet about.

Designed to be called once per cycle. ~1 LLM call. Negligible cost on Groq free tier.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

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


def extract_trending_terms(signals: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Pull concrete searchable terms straight from the scraped signals.

    Strategy:
    - GitHub repo names (e.g. 'open-claw-agents' -> 'open-claw-agents' or just 'open-claw')
    - Distinctive capitalized words from HN/Reddit titles ('Hermes 3', 'Claude Code')
    - Multi-word product-style phrases (TitleCase or Title Case sequences)
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

    # 2) Project/product names from HN + Reddit titles
    #    Capture CapitalCased word sequences (e.g. "Claude Code", "Hermes 3", "GPT-OSS")
    title_sources = [s.get("title", "") for s in signals.get("hackernews", [])[:20]] + \
                    [s.get("title", "") for s in signals.get("reddit", [])[:15]]

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
            if len(terms) >= 20:
                break
        if len(terms) >= 20:
            break

    return terms[:12]


async def fetch_github_recent_hot(client: httpx.AsyncClient, days: int = 14, per_topic: int = 4) -> list[dict[str, Any]]:
    """For each AI topic, fetch recently created repos with the most stars.
    No auth needed; rate-limited to 10 req/min unauth, we stay well under."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    seen: dict[str, dict[str, Any]] = {}
    for topic in _GITHUB_TOPICS:
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


async def fetch_hackernews_ai(client: httpx.AsyncClient, limit: int = 30) -> list[dict[str, Any]]:
    """Top HN stories filtered to AI-relevant by keyword sniffing the title."""
    try:
        r = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10.0)
        ids = r.json()[:60]  # over-fetch, filter down
    except Exception as e:
        logger.debug(f"HN topstories failed: {e}")
        return []

    out: list[dict[str, Any]] = []
    for sid in ids:
        if len(out) >= limit:
            break
        try:
            sr = await client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=10.0)
            s = sr.json() or {}
            title = s.get("title", "")
            if not title:
                continue
            if not _AI_HINT_RE.search(title):
                continue
            out.append({
                "title": title,
                "url": s.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                "score": s.get("score", 0),
                "comments": s.get("descendants", 0),
                "id": sid,
            })
        except Exception:
            continue
    logger.info(f"HN: {len(out)} AI-relevant stories from top {len(ids)}")
    return out


async def fetch_reddit_llm(client: httpx.AsyncClient, limit: int = 15) -> list[dict[str, Any]]:
    """Hot posts from r/LocalLLaMA. Public JSON endpoint, no auth, just needs a UA."""
    out: list[dict[str, Any]] = []
    for sub in ("LocalLLaMA", "singularity"):
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
                out.append({
                    "title": title[:200],
                    "url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "subreddit": sub,
                })
                if len(out) >= limit:
                    break
        except Exception as e:
            logger.debug(f"Reddit {sub} failed: {e}")
    logger.info(f"Reddit: pulled {len(out)} hot posts")
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
    hn = "\n".join(
        f"  - [{s['score']} pts] {s['title']}"
        for s in signals.get("hackernews", [])[:12]
    )
    rd = "\n".join(
        f"  - [r/{s['subreddit']} {s['score']} pts] {s['title']}"
        for s in signals.get("reddit", [])[:8]
    )

    trending_block = "\n".join(f"  - {t}" for t in trending_terms) or "  (none extracted)"

    return f"""NICHE: {niche}

LIVE SIGNAL — GitHub repos (recently created, sorted by stars):
{gh or "  (none)"}

LIVE SIGNAL — HackerNews AI-relevant top stories:
{hn or "  (none)"}

LIVE SIGNAL — Reddit hot in r/LocalLLaMA + r/singularity:
{rd or "  (none)"}

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
- Avoid queries the bot ran in the last few cycles unless the topic is still red-hot.
- If signals are weak, fall back to broad evergreen niche queries.

CRITICAL OUTPUT FORMAT
- Output valid RFC 8259 JSON.
- No prose, no preamble, no code fences (```), no comments (// or /* */), no trailing commas.
- Use straight ASCII double quotes only, never curly quotes.
- Start with {{ and end with }}. Nothing else before or after."""


def _extract_json(text: str) -> dict[str, Any] | None:
    """LLMs sometimes wrap JSON in code fences, add comments, or leave trailing commas.
    Be tolerant: strip fences, drop // and /* */ comments, remove trailing commas, retry."""
    if not text:
        return None
    # Strip code fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"```\s*$", "", text.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        return None
    blob = text[start:end + 1]

    # Pass 1: as-is
    try:
        return json.loads(blob)
    except Exception:
        pass

    # Pass 2: aggressive cleanup
    cleaned = blob
    # Strip // line comments and /* block comments
    cleaned = re.sub(r"//[^\n\r]*", "", cleaned)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    # Drop trailing commas before } or ]
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    # Smart quotes → regular quotes
    cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
    try:
        return json.loads(cleaned)
    except Exception as e:
        logger.warning(f"Strategy JSON parse failed even after cleanup: {e}")
        # Log a small snippet to help diagnose
        logger.debug(f"JSON snippet near failure: {cleaned[:300]}")
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
    """Top-level entrypoint. Pulls signals, calls the LLM, returns a strategy dict.
    Falls back to a safe default on any failure."""
    state["_niche"] = niche  # injected for prompt building

    async with httpx.AsyncClient() as client:
        gh = await fetch_github_recent_hot(client)
        hn = await fetch_hackernews_ai(client)
        rd = await fetch_reddit_llm(client)

    signals = {"github": gh, "hackernews": hn, "reddit": rd}

    # Deterministic trending-term extraction — guaranteed real, signal-derived queries
    trending_terms = extract_trending_terms(signals)
    logger.info(f"Extracted {len(trending_terms)} trending terms: {trending_terms[:8]}")

    prompt = _build_strategy_prompt(state, signals, trending_terms)
    raw = await llm_call(prompt, STRATEGY_SYSTEM)
    parsed = _extract_json(raw or "")
    if not parsed:
        logger.warning("Strategy LLM call failed or unparseable — using default strategy.")
        strategy = _default_strategy()
    else:
        strategy = _validate_strategy(parsed, signals)

    # Force-inject the deterministically extracted trending terms.
    # Belt-and-suspenders: even if LLM ignored the instruction, real trending
    # names still drive a chunk of the reply + like queries this cycle.
    if trending_terms:
        # Reply queries: prepend top 4 trending terms (deduped, keep LLM additions)
        forced = trending_terms[:4]
        existing_lower = {q.lower() for q in strategy["reply_queries"]}
        for term in reversed(forced):
            if term.lower() not in existing_lower:
                strategy["reply_queries"].insert(0, term)
                existing_lower.add(term.lower())
        strategy["reply_queries"] = strategy["reply_queries"][:10]

        # Like queries: half of them should be trending terms too
        like_forced = trending_terms[:3]
        existing_lower = {q.lower() for q in strategy["like_queries"]}
        for term in reversed(like_forced):
            if term.lower() not in existing_lower:
                strategy["like_queries"].insert(0, term)
                existing_lower.add(term.lower())
        strategy["like_queries"] = strategy["like_queries"][:6]

    strategy["_signals"] = signals
    strategy["_trending_terms"] = trending_terms
    return strategy


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
                 {r["url"] for r in signals.get("reddit", [])}
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
