# X / Twitter Automation Bot + Dashboard

A fully autonomous X (Twitter) growth bot with a Next.js control dashboard.

- **bot/** — Python bot (Playwright + Groq/Gemini LLM + RSS news)
- **bot/api_server.py** — FastAPI bridge between bot state and dashboard
- **dashboard/** — Next.js 14 control panel (dark theme, lavender accents)

The bot runs a cycle every ~5 hours: it fetches news, posts 2–3 high-quality tweets, replies to one recent niche tweet, and conservatively follows 1–2 accounts — all with large human-like delays between actions.

---

## 1. One-time setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- An X account you control
- A Groq API key (free): https://console.groq.com
- A Gemini API key (free): https://ai.google.dev

### Install the bot

```bash
cd bot
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS/Linux
pip install -r requirements.txt
python -m playwright install chromium
```

### Configure env

Copy `.env.example` → `.env` in the project root and fill in your API keys:

```env
GROQ_API_KEY=...
GEMINI_API_KEY=...
LLM_PROVIDER=groq
HEADLESS=true
PROXY_URL=
DRY_RUN=false
```

### First login (save cookies)

The bot uses cookie-based login — no passwords stored. Run once in headed mode:

```bash
cd bot
# Windows PowerShell
$env:HEADLESS="false"; python x_automation_bot.py login

# macOS/Linux
HEADLESS=false python x_automation_bot.py login
```

A real Chromium window will open. Log in to X manually. When you reach the home feed, return to the terminal and press **ENTER**. Cookies are saved to `bot/cookies.json`.

### Install the dashboard

```bash
cd ../dashboard
npm install
cp .env.local.example .env.local
```

---

## 2. Running everything (3 terminals)

```bash
# Terminal 1 — Bot
cd bot && python x_automation_bot.py

# Terminal 2 — API bridge
cd bot && uvicorn api_server:app --reload --port 8000

# Terminal 3 — Dashboard
cd dashboard && npm run dev
# Open http://localhost:3000
```

---

## 3. Dashboard

Four pages:

- **/** — status banner, control buttons (Start / Pause / Stop), countdown to next cycle, stats row, recent activity feed
- **/logs** — live SSE-streaming terminal viewer with colored log levels
- **/history** — three tabs (Tweets / Replies / Follows) with full history
- **/settings** — editable cycle limits, LLM provider, and prompt templates

The dashboard polls `/api/status` and `/api/stats` every few seconds via SWR and streams `/api/logs/stream` over Server-Sent Events.

---

## 4. Safety

The bot is **deliberately conservative**:

- Max 3 posts + 1 reply + 2 follows per cycle
- Random 12–35 min between posts, 15–40 min before replies, 25–60 min before follows
- Manual stealth patches applied to every browser context (no `playwright-stealth`)
- Cookie-only login, never stores your password
- Skips selectors gracefully (logs warning + screenshot) instead of crashing
- State persisted in `bot/bot_state.json` so it never reposts or re-replies

Set `DRY_RUN=true` in `.env` to dry-run the full cycle without performing any Playwright actions.

---

## 5. File structure

```
twit-auto/
├── bot/
│   ├── x_automation_bot.py
│   ├── api_server.py
│   ├── prompts/
│   │   ├── tweet_prompt.txt
│   │   └── reply_prompt.txt
│   ├── requirements.txt
│   ├── bot_state.json        (auto-generated)
│   ├── cookies.json          (auto-generated)
│   ├── x_bot.log             (auto-generated)
│   └── debug_screenshots/    (auto-created)
├── dashboard/
│   ├── app/
│   │   ├── page.tsx          # Overview
│   │   ├── logs/page.tsx
│   │   ├── history/page.tsx
│   │   └── settings/page.tsx
│   ├── components/sidebar.tsx
│   ├── lib/api.ts
│   └── package.json
├── .env
└── README.md
```

---

## 6. Notes

- X changes its UI frequently. If posts or replies start failing, check `bot/debug_screenshots/` — the bot saves a screenshot on every selector failure. Update `SELECTORS` at the top of `x_automation_bot.py`.
- For 24/7 long-term use, set a residential `PROXY_URL` in `.env`.
- The first cycle deliberately waits 3–10 minutes before doing anything — this is intentional human-like behavior, not a bug.
