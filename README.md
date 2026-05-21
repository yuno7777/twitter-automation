# Twit-Auto

A fully autonomous X (Twitter) growth bot with a Next.js control dashboard.

- **`bot/`** — Python bot (Playwright + Groq/Gemini LLM + RSS news)
- **`bot/api_server.py`** — FastAPI bridge between the bot's state and the dashboard
- **`dashboard/`** — Next.js 14 control panel with live logs, history, and analytics

Every ~5 hours the bot fetches AI news, generates **1 short thread** (1–3 tweets), posts **5 replies** to recent niche tweets, **likes 10 fresh posts**, and conservatively **follows 1–2 high-quality accounts** — all with large human-like delays and full anti-detection.

---

## Quick start (already-installed machine)

Double-click **`Start Twit-Auto.vbs`** on your desktop. Three processes start silently in the background, the dashboard opens automatically in Chrome once Next.js finishes compiling, and that's it.

To stop everything: double-click **`Stop Twit-Auto.vbs`** on your desktop.

---

## Full setup from scratch

### Prerequisites

- **Windows 10/11** (the launcher VBS is Windows-specific; the Python and Next.js code itself is cross-platform)
- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 18+** — [nodejs.org](https://nodejs.org/)
- **Google Chrome** — needed for the real Chrome browser channel (Playwright's bundled Chromium is detected by X and gets blocked)
- An **X account** you control
- A free **Groq API key** — [console.groq.com](https://console.groq.com)
- A free **Gemini API key** — [aistudio.google.com](https://aistudio.google.com)

### 1. Clone the repo

```powershell
cd "C:\Users\YourName\Desktop\projects"
git clone https://github.com/yuno7777/twitter-automation.git twit-auto
cd twit-auto
```

### 2. Install the bot

```powershell
cd bot
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Configure `.env`

Copy the template:
```powershell
cd ..
copy .env.example .env
```

Open `.env` and fill in:

```env
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
LLM_PROVIDER=groq                 # primary provider — falls back to Gemini on rate limit
HEADLESS=true                     # false only for first login

# Your niche — be specific, this drives every tweet/reply
NICHE=AI agents, LLM workflows, and the gap between AI demos and what actually ships to production. Audience: builders, indie hackers, technical founders.

# Your X handle (no @) — used for self-engagement feedback loop
X_HANDLE=your_handle

# Peak posting hours (24h, local time, comma-separated). Empty = post anytime.
PEAK_HOURS=9,10,13,14,19,20,21

DRY_RUN=false                     # true = log actions but do not actually post/like/follow
```

### 4. First login (one-time, saves cookies)

The bot uses cookie-based login — no password is ever stored.

```powershell
cd bot
$env:HEADLESS="false"
python x_automation_bot.py login
```

A **real Chrome window** opens. Log in to X manually — username, password, any 2FA. The bot watches the URL and **auto-saves cookies** to `cookies.json` once you reach the home feed. Browser closes itself.

Set `HEADLESS=true` back in `.env` afterward.

### 5. Customize your voice (recommended)

Open `bot/prompts/style_notes.txt` and **rewrite it in your own voice**. The defaults are decent, but the LLM is only as good as the personality you give it. Add real opinions, the people you actually read, the tools you actually use. This is the single biggest lever for content quality.

### 6. Install the dashboard

```powershell
cd ..\dashboard
npm install
copy .env.local.example .env.local
```

### 7. Set up the desktop launchers

The repo includes `launcher.ps1` and `stopper.ps1`. You need two thin VBS wrappers on your Desktop so double-clicking is fully silent (no terminal flash).

Create **`C:\Users\YourName\Desktop\Start Twit-Auto.vbs`**:
```vbs
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\YourName\Desktop\projects\twit-auto\launcher.ps1""", 0, False
```

Create **`C:\Users\YourName\Desktop\Stop Twit-Auto.vbs`**:
```vbs
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\YourName\Desktop\projects\twit-auto\stopper.ps1""", 0, False
```

Update the paths in both files to match your machine.

Also update the `$root` path at the top of `launcher.ps1` and `stopper.ps1` to match your project location.

### 8. Run it

Double-click **`Start Twit-Auto.vbs`** on the Desktop. Within 15–30 seconds (or 5 seconds on subsequent runs once Next.js is cached) a Chrome window pops open at `http://localhost:3000`.

---

## Dashboard pages

- **`/`** — Overview: status, control buttons, countdown, stat cards (tweets / replies / likes / follows / LLM calls), recent activity feed
- **`/analytics`** — Daily activity stacked bars, hourly heatmap, top-performing tweets, lifetime totals
- **`/logs`** — SSE-streaming terminal viewer with colored log levels
- **`/history`** — Tabs for Tweets, Replies, Follows with full history
- **`/settings`** — Editable cycle limits, LLM provider, and full prompt templates

---

## How it works — one cycle

Every ~5 hours (with random ±20 min jitter):

1. **Initial human-like delay** — 3–10 min wake-up sleep
2. **Selector health check** — verifies X's UI hasn't changed
3. **Self-engagement scrape** — visits your own profile, extracts top tweets, feeds them into the next LLM prompt as style reference
4. **Like 10 niche tweets** — lowest-risk action, warms the algo
5. **Generate + post 1 thread** (1–3 tweets) — *only if current local hour is in `PEAK_HOURS`*
6. **Post 5 replies** — searches niche, filters to fresh (<90 min) rising (5–500 likes) tweets, replies thoughtfully
7. **Follow 1–2 accounts** — conservatively, with 20-min spacing between

Off-peak hours: posting is skipped, engagement continues.

---

## File structure

```
twit-auto/
├── bot/
│   ├── x_automation_bot.py         # main bot
│   ├── api_server.py               # FastAPI bridge
│   ├── prompts/
│   │   ├── tweet_prompt.txt
│   │   ├── reply_prompt.txt
│   │   └── style_notes.txt         # YOUR voice — edit this
│   ├── requirements.txt
│   ├── bot_state.json              # auto-generated
│   ├── cookies.json                # auto-generated after first login
│   ├── x_bot.log                   # auto-generated
│   ├── chrome_profile/             # auto-generated (Chrome user data dir)
│   └── debug_screenshots/          # auto-created on selector failures
├── dashboard/
│   ├── app/
│   │   ├── page.tsx                # Overview
│   │   ├── analytics/page.tsx
│   │   ├── logs/page.tsx
│   │   ├── history/page.tsx
│   │   └── settings/page.tsx
│   ├── components/sidebar.tsx
│   ├── lib/api.ts                  # typed API client
│   └── package.json
├── logs/                           # launcher runtime logs (auto-created)
├── launcher.ps1                    # silent multi-process launcher
├── stopper.ps1                     # silent killer
├── .env                            # your secrets — git-ignored
├── .env.example
└── README.md
```

---

## Troubleshooting

### Dashboard says "offline" after running the launcher
- Check `logs/launcher.err.log`
- Check `logs/dashboard.log` for Next.js compile errors
- Check `logs/api.log` for Python errors
- Run the stop script, then start again — sometimes a previous run left stale processes

### Bot logs say "selector failed"
- X changes its UI. Open `bot/debug_screenshots/` to see what the bot saw
- Update the `SELECTORS` dict at the top of `bot/x_automation_bot.py`

### Login flow loops back to the login page
- X blocks Playwright's bundled Chromium. Make sure you're using `channel="chrome"` — the code does this by default. Just confirm real Google Chrome is installed.

### Account suspended
- Check `bot/x_bot.log` for the rate at which you were posting/following
- Lower `MAX_REPLIES_PER_CYCLE` and `MAX_FOLLOWS_PER_CYCLE` in `.env`
- Wait, appeal, and consider a residential proxy via `PROXY_URL` for the next account

---

## Safety knobs

All in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `MAX_POSTS_PER_CYCLE` | 1 | Tweets/threads per cycle |
| `MAX_REPLIES_PER_CYCLE` | 5 | Replies per cycle — highest growth lever |
| `MAX_LIKES_PER_CYCLE` | 10 | Likes per cycle — lowest-risk action |
| `MAX_FOLLOWS_PER_CYCLE` | 2 | Follows per cycle — keep low |
| `PEAK_HOURS` | `9,10,13,14,19,20,21` | When posting is allowed |
| `DRY_RUN` | `false` | Log without actually performing actions |
| `PROXY_URL` | empty | Residential proxy for long-term use |

Start conservative on a fresh account. Ramp up after a healthy week.

---

## Manual run (without the launcher)

Three terminals:

```powershell
# Terminal 1 — bot
cd bot && python x_automation_bot.py

# Terminal 2 — API bridge
cd bot && python -m uvicorn api_server:app --reload --port 8000

# Terminal 3 — dashboard
cd dashboard && npm run dev
```

Open http://localhost:3000

---

## Tech stack

| Layer | Tools |
|---|---|
| Browser automation | Playwright (real Chrome via `channel="chrome"` + persistent profile) |
| LLM | Groq `llama-3.3-70b-versatile` (primary) with Gemini `1.5-flash` fallback |
| News | `feedparser` over 6 RSS feeds |
| Backend | FastAPI + Uvicorn |
| Frontend | Next.js 14, Tailwind, Recharts, shadcn-style components, SWR |
| Stealth | Manual `add_init_script` patches (no `playwright-stealth`) |
| State | Single `bot_state.json` file, atomic write |
