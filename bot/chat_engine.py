"""
Agentic chat engine for the dashboard.

A Gemini-powered assistant that can see the entire bot brain (state, stats,
critic decisions, recent activity, performance) and PROPOSE configuration
changes that the user approves in the UI before they take effect.

Design:
  - Runs in the API-server process (isolated from the bot's Groq budget).
  - Every chat turn gets a fresh "bot context" blob injected, so the model
    always has live data — no multi-turn tool-calling dance.
  - The model replies with strict JSON: {reply, proposed_actions[]}.
  - Read access is implicit (context is in the prompt). Writes are proposals
    the user must confirm; confirmation routes through apply_action().

Nothing here ever touches the live X account directly — it only edits
bot_state.json and .env, which the bot picks up on its next cycle.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOT_DIR = Path(__file__).resolve().parent
ROOT_DIR = BOT_DIR.parent
ENV_PATH = ROOT_DIR / ".env"
VIP_PATH = BOT_DIR / "vip_handles.txt"

GEMINI_MODEL = os.getenv("CHAT_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Multimodal attachment limits (inline data — keep well under Gemini's request cap)
MAX_ATTACHMENT_BYTES = 6 * 1024 * 1024   # 6 MB per file
MAX_ATTACHMENTS = 4
SUPPORTED_ATTACHMENT_MIMES = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/heic", "image/heif",
    "application/pdf",
    "text/plain", "text/markdown", "text/csv",
}

# Tuning knobs the chat agent is allowed to change. Anything not on this
# allowlist is rejected even if the model proposes it.
ALLOWED_KNOBS = {
    "MAX_REPLIES_PER_CYCLE": (int, 0, 20),
    "MAX_QUOTES_PER_CYCLE": (int, 0, 10),
    "MAX_REPOSTS_PER_CYCLE": (int, 0, 10),
    "MAX_FOLLOWS_PER_CYCLE": (int, 0, 10),
    "MAX_LIKES_PER_CYCLE": (int, 0, 30),
    "MAX_FOLLOW_UPS_PER_CYCLE": (int, 0, 10),
    "MAX_POSTS_PER_CYCLE": (int, 0, 5),
    "MAX_DAILY_ACTIONS": (int, 10, 500),
    "VIP_REPLY_RATIO": (float, 0.0, 1.0),
    "VIP_MAX_AGE_MIN": (int, 15, 360),
    "MAX_ACTIONS_PER_VIP_PER_CYCLE": (int, 1, 5),
    "MAX_ACTIONS_PER_VIP_PER_DAY": (int, 1, 10),
}

# Tool surface advertised to the model. Read tools are not listed because
# their data is already injected as context; only writes need proposing.
TOOL_SPEC = """
AVAILABLE ACTIONS (you PROPOSE these; the user approves before they run):

1. set_knob        — change a tuning knob.
   args: {"key": "<KNOB_NAME>", "value": <number>}
   valid keys: MAX_REPLIES_PER_CYCLE, MAX_QUOTES_PER_CYCLE, MAX_REPOSTS_PER_CYCLE,
   MAX_FOLLOWS_PER_CYCLE, MAX_LIKES_PER_CYCLE, MAX_FOLLOW_UPS_PER_CYCLE,
   MAX_POSTS_PER_CYCLE, MAX_DAILY_ACTIONS, VIP_REPLY_RATIO, VIP_MAX_AGE_MIN,
   MAX_ACTIONS_PER_VIP_PER_CYCLE, MAX_ACTIONS_PER_VIP_PER_DAY

2. add_vip         — add a handle to the VIP list. args: {"handle": "<handle no @>"}
3. remove_vip      — remove a handle from the VIP list. args: {"handle": "<handle>"}
4. add_avoid_phrase    — add a phrase the generator must avoid. args: {"phrase": "<text>"}
5. add_topic_id    — add a topic tag to the rotation. args: {"topic": "<text>"}
6. remove_topic_id — remove a topic tag. args: {"topic": "<text>"}
7. bot_control     — control the bot. args: {"action": "pause" | "resume" | "reset_cycle"}
8. enqueue_tweet   — drop a manual draft into the approval queue. args: {"text": "<tweet text>"}
9. remember        — save a durable fact/preference about the owner that should
   persist across ALL chat sessions. args: {"fact": "<concise fact>"}
   Use this when the owner states a lasting preference ("I prefer quotes over
   replies", "my niche is dev tools", "never post on weekends").

Only propose an action when the owner clearly wants a change OR you are
confident it fixes a problem visible in the context. Always explain WHY in
the "reason" field. Never propose editing prompt files or code.
"""

SYSTEM_PROMPT = """You are Friday — the co-pilot for the owner's autonomous X
(Twitter) growth bot. Think of yourself as their sharp, in-the-loop teammate,
not a corporate assistant. You can SEE the bot's live state, stats, recent
activity, critic decisions, and performance (all provided below as context),
plus anything in persistent_memory you've learned about them.

VOICE — talk like a smart friend who happens to run their growth bot:
- Warm and casual, but substantive. Contractions, plain English, no corporate
  filler ("I'd suggest", "it is recommended"). Say "let's", "honestly",
  "here's the thing", "nice", "yeah" when it fits.
- Direct and opinionated. Have a take. If the data says something, call it.
- Honest about trade-offs — never hype. If a request is a bad idea (cranking
  volume past safe limits, reposting off-niche, muted keywords), push back
  plainly and explain why, then offer the better move.
- Concise. This is a chat bubble, not an essay. A couple tight sentences beats a
  wall of text. Lead with the answer, then the why.
- Cite the actual numbers from the context when you reference performance.
- A little dry wit is welcome; never cheesy, never emoji-spam (one emoji max,
  and only if it lands).
- Address them as "you". Remember their preferences from persistent_memory and
  act like you actually know them.

You understand the X algorithm cold: quotes distribute to your own followers,
replies need conversation reach, the diversity multiplier penalizes repeated
authors, muted keywords make tweets invisible, and the first line decides dwell.

You PROPOSE configuration changes but never apply them yourself — the owner taps
Apply in the UI. Approved changes hit the bot on its next cycle (or right away
if they Reset Cycle), so it's fine to say "I'll line it up for the next cycle."

You MUST respond with STRICT JSON only — no markdown fences, no prose outside
the JSON. Schema:
{
  "thinking": "<2-4 sentences of honest reasoning: what they need, what the data
               shows, why you're proposing what you are. Shown in a collapsible
               'thought process' panel.>",
  "reply": "<your message to the owner, in Friday's voice>",
  "proposed_actions": [
    {"tool": "<tool name>", "args": {...}, "reason": "<why this helps>"}
  ]
}
If there's nothing to change, return "proposed_actions": [].
"""


def _read_state() -> dict[str, Any]:
    path = BOT_DIR / "bot_state.json"
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    path = BOT_DIR / "bot_state.json"
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _tail_log(n: int = 25) -> list[str]:
    log = BOT_DIR / "x_bot.log"
    if not log.exists():
        return []
    try:
        with log.open("r", encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f.readlines()[-n:]]
    except Exception:
        return []


def build_bot_context() -> str:
    """Assemble a compact snapshot of everything the agent should know."""
    s = _read_state()
    stats = s.get("stats", {})
    settings = {
        k: os.getenv(k, "?") for k in (
            "MAX_REPLIES_PER_CYCLE", "MAX_QUOTES_PER_CYCLE", "MAX_REPOSTS_PER_CYCLE",
            "MAX_FOLLOWS_PER_CYCLE", "MAX_LIKES_PER_CYCLE", "VIP_REPLY_RATIO",
            "VIP_MAX_AGE_MIN", "MAX_DAILY_ACTIONS", "MAX_ACTIONS_PER_VIP_PER_DAY",
        )
    }

    def _slim(items: list[dict], keys: list[str], n: int = 8) -> list[dict]:
        return [{k: it.get(k) for k in keys if k in it} for it in (items or [])[:n]]

    critic = _slim(s.get("critic_log", []), ["role", "score", "issues", "accepted", "ts"], 10)
    tweets = _slim(s.get("tweet_history", []), ["text", "posted_at"], 5)
    replies = _slim(s.get("reply_history", []), ["reply_text", "original_tweet_url", "posted_at"], 5)
    perf = _slim(s.get("own_tweet_performance", []), ["text", "likes", "replies", "reposts"], 6)
    nudges = [n for n in (s.get("ai_nudges") or []) if not n.get("dismissed")][:8]
    avoid = (s.get("phrases_to_avoid") or [])[:15]

    ctx = {
        "status": s.get("status"),
        "current_action": s.get("current_action"),
        "next_cycle_at": s.get("next_cycle_at"),
        "daily_action_count": s.get("daily_action_count"),
        "stats": stats,
        "current_settings": settings,
        "persistent_memory": s.get("chat_memory") or [],  # facts learned across all sessions
        "recent_critic_decisions": critic,
        "recent_tweets": tweets,
        "recent_replies": replies,
        "own_tweet_performance": perf,
        "active_nudges": nudges,
        "phrases_to_avoid": avoid,
        "recent_log_tail": _tail_log(15),
    }
    return json.dumps(ctx, ensure_ascii=False, default=str)


async def _call_gemini(parts: list[Any]) -> str | None:
    """parts: a list of prompt parts — strings and/or {'mime_type','data'} blobs
    for images/PDFs/text files (Gemini multimodal input)."""
    if not GEMINI_API_KEY:
        return None
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)
    result = await asyncio.to_thread(model.generate_content, parts)
    return (result.text or "").strip()


def _validate_attachments(attachments: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """Returns (valid_parts, rejected_names). Each valid part is a Gemini blob
    dict {'mime_type', 'data': bytes}."""
    if not attachments:
        return [], []
    parts: list[dict[str, Any]] = []
    rejected: list[str] = []
    for att in attachments[:MAX_ATTACHMENTS]:
        name = att.get("name", "file")
        mime = (att.get("mime") or "").lower()
        data = att.get("data")  # already-decoded bytes
        if mime not in SUPPORTED_ATTACHMENT_MIMES:
            rejected.append(f"{name} (unsupported type {mime or '?'})")
            continue
        if not data or len(data) > MAX_ATTACHMENT_BYTES:
            rejected.append(f"{name} (too large or empty)")
            continue
        parts.append({"mime_type": mime, "data": data})
    return parts, rejected


def _parse_response(raw: str) -> dict[str, Any]:
    """Reuse the bot's hardened JSON extractor; fall back to plain text."""
    try:
        from intelligence import _extract_json
        parsed = _extract_json(raw or "")
    except Exception:
        parsed = None
    if not parsed:
        # Model returned prose — treat the whole thing as the reply
        return {"thinking": "", "reply": (raw or "").strip() or "(no response)", "proposed_actions": []}
    parsed.setdefault("thinking", "")
    parsed.setdefault("reply", "")
    parsed.setdefault("proposed_actions", [])
    if not isinstance(parsed["proposed_actions"], list):
        parsed["proposed_actions"] = []
    return parsed


async def chat(
    messages: list[dict[str, str]],
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """messages: [{role: 'user'|'assistant', content: str}, ...] newest last.
    attachments: optional list of {name, mime, data:bytes} for the CURRENT turn —
    images/PDFs/text the model should analyze.
    Returns {reply, proposed_actions:[{id, tool, args, reason}]}."""
    context = build_bot_context()
    convo = "\n".join(
        f"{'OWNER' if m.get('role') == 'user' else 'YOU'}: {m.get('content', '')}"
        for m in messages[-12:]
    )
    att_parts, rejected = _validate_attachments(attachments)
    att_note = ""
    if att_parts:
        att_note = (
            f"\n\nThe owner attached {len(att_parts)} file(s) (shown below as media parts). "
            f"Analyze them in the context of the bot — e.g. an X analytics screenshot, a "
            f"competitor's tweet, a document of ideas. Extract concrete takeaways and, where "
            f"relevant, propose actions."
        )
    if rejected:
        att_note += f"\n\n(Rejected attachments: {', '.join(rejected)}.)"

    prompt = (
        f"{SYSTEM_PROMPT}\n\n{TOOL_SPEC}\n\n"
        f"=== LIVE BOT CONTEXT (JSON) ===\n{context}\n\n"
        f"=== CONVERSATION ===\n{convo}{att_note}\n\n"
        f"Respond now with the strict JSON schema."
    )
    # Multimodal: text prompt first, then any media blobs
    parts: list[Any] = [prompt] + att_parts
    raw = await _call_gemini(parts)
    if raw is None:
        return {
            "thinking": "",
            "reply": "Chat is unavailable — no GEMINI_API_KEY is configured for the API server.",
            "proposed_actions": [],
        }
    parsed = _parse_response(raw)

    # Validate + stamp each proposed action with an id so the UI can confirm it
    clean_actions = []
    for a in parsed.get("proposed_actions", []):
        if not isinstance(a, dict) or "tool" not in a:
            continue
        ok, err = _validate_action(a.get("tool"), a.get("args") or {})
        clean_actions.append({
            "id": uuid.uuid4().hex[:12],
            "tool": a.get("tool"),
            "args": a.get("args") or {},
            "reason": a.get("reason", ""),
            "valid": ok,
            "validation_error": err,
        })

    return {
        "thinking": parsed.get("thinking", ""),
        "reply": parsed.get("reply", ""),
        "proposed_actions": clean_actions,
    }


# ---------------------------------------------------------------------------
# Action validation + application
# ---------------------------------------------------------------------------

def _validate_action(tool: str, args: dict[str, Any]) -> tuple[bool, str | None]:
    if tool == "set_knob":
        key = args.get("key")
        if key not in ALLOWED_KNOBS:
            return False, f"'{key}' is not a permitted tuning knob."
        caster, lo, hi = ALLOWED_KNOBS[key]
        try:
            v = caster(args.get("value"))
        except Exception:
            return False, f"value for {key} must be a {caster.__name__}."
        if not (lo <= v <= hi):
            return False, f"{key} must be between {lo} and {hi}."
        return True, None
    if tool in ("add_vip", "remove_vip"):
        h = str(args.get("handle", "")).lstrip("@").strip()
        if not h or len(h) > 15 or not h.replace("_", "").isalnum():
            return False, "handle looks invalid."
        return True, None
    if tool == "add_avoid_phrase":
        if not str(args.get("phrase", "")).strip():
            return False, "phrase is empty."
        return True, None
    if tool in ("add_topic_id", "remove_topic_id"):
        if not str(args.get("topic", "")).strip():
            return False, "topic is empty."
        return True, None
    if tool == "bot_control":
        if args.get("action") not in ("pause", "resume", "reset_cycle"):
            return False, "action must be pause/resume/reset_cycle."
        return True, None
    if tool == "enqueue_tweet":
        t = str(args.get("text", "")).strip()
        if not t or len(t) > 280:
            return False, "tweet text must be 1-280 chars."
        return True, None
    if tool == "remember":
        f = str(args.get("fact", "")).strip()
        if not f or len(f) > 240:
            return False, "fact must be 1-240 chars."
        return True, None
    return False, f"unknown tool '{tool}'."


def apply_action(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a user-approved action. Returns {ok, message}."""
    ok, err = _validate_action(tool, args)
    if not ok:
        return {"ok": False, "message": err or "invalid action"}

    from dotenv import set_key

    if tool == "set_knob":
        key = args["key"]
        caster, _, _ = ALLOWED_KNOBS[key]
        val = str(caster(args["value"]))
        if not ENV_PATH.exists():
            ENV_PATH.write_text("", encoding="utf-8")
        set_key(str(ENV_PATH), key, val)
        os.environ[key] = val
        msg = f"Set {key} = {val} (takes effect next cycle)."

    elif tool in ("add_vip", "remove_vip"):
        handle = str(args["handle"]).lstrip("@").strip()
        lines = VIP_PATH.read_text(encoding="utf-8").splitlines() if VIP_PATH.exists() else []
        existing = {ln.strip().lstrip("@").lower() for ln in lines if ln.strip() and not ln.startswith("#")}
        if tool == "add_vip":
            if handle.lower() in existing:
                return {"ok": False, "message": f"@{handle} is already a VIP."}
            lines.append(handle)
            msg = f"Added @{handle} to the VIP list."
        else:
            lines = [ln for ln in lines if ln.strip().lstrip("@").lower() != handle.lower()]
            msg = f"Removed @{handle} from the VIP list."
        VIP_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    elif tool == "add_avoid_phrase":
        s = _read_state()
        avoid = s.setdefault("phrases_to_avoid", [])
        p = str(args["phrase"]).strip().lower()
        if p not in avoid:
            avoid.insert(0, p)
        s["phrases_to_avoid"] = avoid[:50]
        _write_state(s)
        msg = f"Added avoid-phrase: '{p}'."

    elif tool in ("add_topic_id", "remove_topic_id"):
        s = _read_state()
        topics = s.setdefault("custom_topic_ids", [])
        t = str(args["topic"]).strip()
        if tool == "add_topic_id":
            if t not in topics:
                topics.insert(0, t)
            msg = f"Added topic '{t}'."
        else:
            topics = [x for x in topics if x.lower() != t.lower()]
            msg = f"Removed topic '{t}'."
        s["custom_topic_ids"] = topics[:30]
        _write_state(s)

    elif tool == "bot_control":
        s = _read_state()
        action = args["action"]
        if action == "pause":
            s["status"] = "paused"
        elif action == "resume":
            s["status"] = "running"
        elif action == "reset_cycle":
            s["status"] = "running"
            s["force_new_cycle"] = True
        _write_state(s)
        msg = f"Bot control: {action}."

    elif tool == "enqueue_tweet":
        s = _read_state()
        q = s.setdefault("draft_queue", [])
        q.insert(0, {
            "id": uuid.uuid4().hex[:12],
            "kind": "manual_chat",
            "thread": [str(args["text"]).strip()],
            "title": "Manual draft from chat",
            "source_url": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        s["draft_queue"] = q[:100]
        _write_state(s)
        msg = "Queued a manual draft — review it on the Queue page."

    elif tool == "remember":
        s = _read_state()
        mem = s.setdefault("chat_memory", [])
        fact = str(args["fact"]).strip()
        if fact not in mem:
            mem.insert(0, fact)
        s["chat_memory"] = mem[:60]
        _write_state(s)
        msg = f"Saved to memory: '{fact}'."
    else:
        return {"ok": False, "message": f"unknown tool '{tool}'"}

    # Audit trail
    s = _read_state()
    log = s.setdefault("ai_actions_log", [])
    log.insert(0, {
        "tool": tool, "args": args, "message": msg,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    })
    s["ai_actions_log"] = log[:200]
    _write_state(s)
    return {"ok": True, "message": msg}
