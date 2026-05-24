<div align="center">

<br />

# Twitter Growth System

<sub>**[ autonomous · trend-aware · self-pacing ]**</sub>

<br />

#### A complete X / Twitter growth system that researches what's actually trending before it speaks.

<sub>Built for builders who'd rather ship code than schedule tweets.</sub>

<br />

![Python](https://img.shields.io/badge/python-3.11+-000000?style=flat-square&logo=python&logoColor=white&labelColor=000)
![Next.js](https://img.shields.io/badge/next.js-14-000000?style=flat-square&logo=next.js&logoColor=white&labelColor=000)
![FastAPI](https://img.shields.io/badge/fastapi-0.115-000000?style=flat-square&logo=fastapi&logoColor=white&labelColor=000)
![Playwright](https://img.shields.io/badge/playwright-1.49-000000?style=flat-square&logo=playwright&logoColor=white&labelColor=000)
![TypeScript](https://img.shields.io/badge/typescript-5-000000?style=flat-square&logo=typescript&logoColor=white&labelColor=000)
![Tailwind](https://img.shields.io/badge/tailwind-3.4-000000?style=flat-square&logo=tailwindcss&logoColor=white&labelColor=000)

<br />

![status](https://img.shields.io/badge/status-running_24%2F7-A78BFA?style=flat-square&labelColor=000)
![license](https://img.shields.io/badge/license-MIT-A78BFA?style=flat-square&labelColor=000)
![cost](https://img.shields.io/badge/runtime_cost-%240-A78BFA?style=flat-square&labelColor=000)
![stealth](https://img.shields.io/badge/stealth-real_chrome-A78BFA?style=flat-square&labelColor=000)

<br />

`╌────────────────────────────────────────────────────────╌`

</div>

<br />

<br />

## One-prompt setup

<sub>Have an AI coding agent (Claude Code, Cursor, Windsurf, Aider, etc.) set this whole thing up for you. Copy the block below into your agent's prompt, hit enter, answer the questions when it asks.</sub>

<br />

```
You are setting up the Twitter Growth System on my Windows machine.
Repo: https://github.com/yuno7777/twitter-automation

Follow these steps in order. Stop and ASK me when you need input.

STEP 1 — Clone
- Clone the repo to C:\Users\<me>\Desktop\projects\twitter-growth-system
  (substitute my actual Windows username for <me> — ask me if unsure)

STEP 2 — Verify prerequisites
- Confirm Python 3.11+, Node.js 18+, and Google Chrome are installed.
  If any are missing, STOP and tell me what to install.

STEP 3 — Install bot dependencies
- cd bot
- pip install -r requirements.txt
- python -m playwright install chromium

STEP 4 — Configure .env
- ASK ME for these values, one by one:
  1. GROQ_API_KEY  (free at console.groq.com)
  2. GEMINI_API_KEY  (free at aistudio.google.com)
  3. X_HANDLE  (my Twitter/X username without the @)
  4. NICHE  (1-2 sentences — what my account is about)
- Copy .env.example to .env at the project root
- Fill in the values I gave you. Leave PROXY_URL empty.
- Keep HEADLESS=true and DRY_RUN=false.

STEP 5 — Customize voice
- Open bot/prompts/style_notes.txt
- ASK ME 3 questions:
  a) Who am I writing as (builder, founder, researcher, etc.)?
  b) Name 2-3 opinions I actually hold about AI/tech.
  c) Name 2-3 tools I actually use day-to-day (Claude, Cursor, n8n, etc.).
- Rewrite the style_notes.txt file using my answers. Keep the existing
  structure (WHO I AM / HOW I WRITE / OPINIONS I HOLD / THINGS I NEVER SAY)
  but make every line authentic to me.

STEP 6 — First-time X login (this requires me)
- Run: cd bot ; $env:HEADLESS="false" ; python x_automation_bot.py login
- A real Chrome window will open. STOP and tell me to log in manually.
- Wait for me to confirm I've reached the home feed before continuing.
- The bot will auto-save cookies to bot/cookies.json.

STEP 7 — Install dashboard
- cd ../dashboard
- npm install
- Copy .env.local.example to .env.local

STEP 8 — Wire up the launcher paths
- Open launcher.ps1 and stopper.ps1 at the project root.
- Update the $root variable at the top of each to match the actual project path
  on my machine (use the path from Step 1).

STEP 9 — Create desktop shortcuts
- Create C:\Users\<me>\Desktop\Start Twitter Growth.vbs containing:
    Set sh = CreateObject("WScript.Shell")
    sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""<full path to launcher.ps1>""", 0, False
- Create C:\Users\<me>\Desktop\Stop Twitter Growth.vbs the same way,
  pointing at stopper.ps1.
- Substitute the real absolute paths — no <placeholders>.

STEP 10 — First launch
- Double-click Start Twitter Growth.vbs (or run the VBS via wscript)
- Tell me to wait 15-30 seconds for Chrome to open the dashboard at
  http://localhost:3000

STEP 11 — Verify
- Confirm the dashboard loads, the status pill shows RUNNING, and the
  Memory page populates within a few minutes.

If any step fails, show me the exact error from logs/bot.log, logs/api.log,
or logs/dashboard.log and propose a fix before continuing.
```

<br />

<sub>Once it's running, the rest of the README is reference — skip to **Dashboard** below to see what each page does.</sub>

<br />

---

<br />

```
   Every 2 hours, autonomously:

   ▸  researches    →   GitHub trending · HackerNews · Reddit r/LocalLLaMA · 5 AI newsletters
   ▸  writes        →   1–3 tweet thread in your voice, grounded in real source URLs
   ▸  attaches      →   pulls og:image from the article/repo and posts it with the thread
   ▸  critiques     →   every draft scored 1–10 (hook · voice · value · grounding) before posting
   ▸  engages       →   5 thoughtful replies, LLM-filtered (no spam/ragebait/off-topic)
   ▸  quotes        →   1 viral post per cycle with a sharper take
   ▸  follows up    →   continues conversations on your own tweets (sentiment-checked)
   ▸  likes         →   10 niche tweets to warm the algo signal
   ▸  follows       →   1–2 high-quality accounts — biased toward followers-of-creators-you-admire
   ▸  drafts        →   off-peak hours generate tweets to your approval queue
   ▸  learns        →   tracks own top + bottom performers, biases toward what works
   ▸  studies       →   scrapes tracked creators in your niche for live style reference
   ▸  varies        →   rotates 6 content modes (hook · story · contrarian · listicle · question · comparison)
   ▸  monitors      →   own account health each cycle — auto-pauses if X shows suspension/limit
   ▸  adapts        →   exponential backoff (1x→8x) when X throttles, resets on clean cycle
```

<br />

> No paid X API. No paid LLM. No proxy required.
> Just a real Chrome browser, a free Groq + Gemini key, and ~110 minutes of
> spread-out activity per cycle.

<br />

---

<br />

## What makes it different

<table>
<tr>
<td width="33%" valign="top">

#### ◆ real trend discovery

Scrapes **GitHub recent-hot repos**, **HackerNews AI stories**, and **Reddit r/LocalLLaMA + r/singularity** every cycle. An LLM strategy brain decides what to search on X based on what's trending *right now* — not a hardcoded list.

</td>
<td width="33%" valign="top">

#### ◆ pre-flight tweet critic

Every draft (tweet, reply, quote, follow-up) is scored 1–10 on hook strength, voice match, and value by a second LLM call. Score below 7? Auto-regenerated up to 3 times.

</td>
<td width="33%" valign="top">

#### ◆ smart reply candidate analyzer

Doesn't just pick the most-liked tweet. LLM classifies each candidate (`spam · giveaway · ragebait · genuine`), reads sentiment, and picks the one worth replying to with the right reply style.

</td>
</tr>
<tr>
<td valign="top">

#### ◆ engagement learning loop

Scrapes your own top **and** bottom-performing tweets each cycle. Both get fed into the next prompt — *"write more like these, avoid those."* The bot compounds toward what works for *your* audience.

</td>
<td valign="top">

#### ◆ quote-tweet capability

Finds viral fresh tweets in your niche, generates a sharper take, posts as a quote-tweet. Quote-tweets get 2–3× the reach of plain replies on X.

</td>
<td valign="top">

#### ◆ conversation continuation

When someone replies to your tweet, the bot drafts a thoughtful follow-up. Sentiment-filtered: skips anything hostile or sarcastic. Max one follow-up per thread.

</td>
</tr>
<tr>
<td valign="top">

#### ◆ off-hours draft queue

During off-peak hours, the bot drafts tweets to a queue instead of posting blindly. Wake up, review them on `/queue`, approve / edit / reject. Approved drafts post automatically next peak hour.

</td>
<td valign="top">

#### ◆ 3-tier LLM cascade with rate-limit memory

`gpt-oss-120b` → `llama-3.3-70b` → `gemini-2.5`. **Two Groq API keys** for separate rate budgets per tier. When a model 429s, the bot **records the cooldown** and skips it until it recovers — no wasted requests.

</td>
<td valign="top">

#### ◆ anti-hallucination grounding

Every tweet must include its source URL. Critic has a dedicated `grounding` axis — a community repo presented as an official launch, an unverifiable benchmark, or an ambiguous product name gets auto-rejected and regenerated.

</td>
</tr>
<tr>
<td valign="top">

#### ◆ account health monitor

Each cycle scrapes your own profile. Detects `suspension`, `limited`, `verify required` warnings and follower-count drops. Auto-pauses the bot on critical. Banner on the dashboard.

</td>
<td valign="top">

#### ◆ best-time-to-post auto-detect

`/api/optimal_hours` analyzes your tweet history × engagement and surfaces the hours your audience actually responds. Shown next to current `PEAK_HOURS` on `/analytics`.

</td>
<td valign="top">

#### ◆ real chrome, not headless

X aggressively blocks Playwright's bundled Chromium. Uses your installed Chrome with a persistent user-data-dir. **Cookie-based login, no password ever stored.**

</td>
</tr>
<tr>
<td valign="top">

#### ◆ followers-of-creators discovery

60% of follow phases visit a tracked creator's `/followers` page instead of generic search. Same-niche audience signal → way higher follow-back rate.

</td>
<td valign="top">

#### ◆ eval harness

`bot/evals/tweet_eval.jsonl` + `eval_runner.py`. Score any model / prompt change against 10 labeled scenarios including an adversarial pump-fraud prompt. Use `--compare A,B` for A/B model bake-offs.

</td>
<td valign="top">

#### ◆ one-click launcher

Double-click a `.vbs` on your Desktop → 3 hidden background processes start → Chrome auto-opens to the dashboard. Zero terminal flash, zero taskbar clutter.

</td>
</tr>
</table>

<br />

---

<br />

## Architecture

```mermaid
flowchart LR
    A[GitHub API<br/>recent hot repos] --> S
    B[HackerNews<br/>top AI stories] --> S
    C[Reddit JSON<br/>hot ML posts] --> S
    N[5 AI Newsletters<br/>AINews · Latent Space ...] --> S
    CR[Creator profiles<br/>top tweets scrape] --> S

    S[Strategy Brain<br/>3-tier LLM cascade<br/>gpt-oss-120b → llama-3.3 → gemini-2.5<br/>w/ rate-limit memory] --> Q[Reply / Like / Follow queries<br/>Tweet topics + repos<br/>Trending terms]

    Q --> CR2[Pre-flight Critic<br/>hook · voice · value · grounding]
    CR2 --> P[Playwright<br/>Real Chrome<br/>Stealth Patches]
    P --> X[X / Twitter]
    P --> M[(bot_state.json<br/>Persistent Memory)]
    M --> S

    API[FastAPI Bridge<br/>:8000] <--> M
    UI[Next.js Dashboard<br/>:3000] <--> API
```

<br />

---

<br />

## Quick start

<sub>Already set up? Double-click **`Start Twit-Auto.vbs`** on your desktop. Done.</sub>

<details>
<summary><b>First-time setup — click to expand</b></summary>

<br />

### Prerequisites

| requirement | why |
|---|---|
| Windows 10/11 | launcher VBS is Windows-specific (the code itself is cross-platform) |
| Python 3.11+ | bot runtime |
| Node.js 18+ | dashboard |
| Google Chrome | real browser channel (bundled Chromium gets blocked by X) |
| an X account | yours to control |
| Groq API key *(free)* | primary LLM — [console.groq.com](https://console.groq.com) |
| Gemini API key *(free)* | rate-limit fallback — [aistudio.google.com](https://aistudio.google.com) |

### 1. Clone

```bash
git clone https://github.com/yuno7777/twitter-automation.git twit-auto
cd twit-auto
```

### 2. Bot deps

```powershell
cd bot
pip install -r requirements.txt
python -m playwright install chromium
```

### 3. Configure `.env` *(project root)*

```env
GROQ_API_KEY=your_groq_key
GEMINI_API_KEY=your_gemini_key
LLM_PROVIDER=groq
HEADLESS=true

# Be specific — this drives every tweet
NICHE=AI agents, LLM workflows, and the gap between AI demos and what actually ships to production.

X_HANDLE=your_handle_no_at
PEAK_HOURS=9,10,13,14,19,20,21
DRY_RUN=false
```

### 4. First login *(saves cookies)*

```powershell
cd bot
$env:HEADLESS="false"
python x_automation_bot.py login
```

A real Chrome window opens. Log in manually. The bot auto-saves cookies once you reach the home feed.

### 5. Customize your voice

Open `bot/prompts/style_notes.txt` and **rewrite it in your own voice**. Single biggest lever for tweet quality.

### 6. Dashboard deps

```powershell
cd ../dashboard
npm install
copy .env.local.example .env.local
```

### 7. Desktop launchers

Place these two files on your Desktop:

**`Start Twit-Auto.vbs`**
```vbs
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\path\to\twit-auto\launcher.ps1""", 0, False
```

**`Stop Twit-Auto.vbs`**
```vbs
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\path\to\twit-auto\stopper.ps1""", 0, False
```

Update the paths. Also update `$root` at the top of `launcher.ps1` and `stopper.ps1`.

### 8. Launch

Double-click **`Start Twit-Auto.vbs`**. In 5–30 seconds, Chrome opens to `http://localhost:3000`.

</details>

<br />

---

<br />

## The dashboard

<div align="center">

<sub>Five pages. Dark theme. Lavender accents. Glassmorphism.</sub>

</div>

<br />

| page  | what it shows |
|:------|:---|
| `/`              | status, control buttons (start / pause / stop / **reset cycle**), countdown, stat row, recent activity. Banners for: account-health critical/warning, adaptive backoff active, cookie refresh, LLM-tier exhaustion |
| `/memory`        | live trending terms, current strategy, queued tweet angles, GitHub repos on radar, **creator intel**, **pre-flight critic log** |
| `/queue`         | **off-hours drafts pending your approval** — approve / edit / reject before they post |
| `/analytics`     | daily activity stacked bars, hourly heatmap, your top-performing tweets, **optimal posting hours** (auto-detected) |
| `/logs`          | Server-Sent Events stream of `x_bot.log` with colored levels |
| `/history`       | tweets · replies · **quotes** · **follow-ups** · follows tabs |
| `/settings`      | **3-tier LLM cascade picker** (per-tier model + API key status), cycle limits, full prompt templates |

<br />

---

<br />

## One cycle, end to end

```
   T+0     initial wake-up delay (1 min)
   T+1     account-health check     (scrape own profile — auto-pause if X warns)
   T+2     self-engagement scrape   (read own top + bottom tweets)
   T+2     creator intel scrape     (top tweets from CREATORS_TO_STUDY)
   T+3     strategy synthesis       (signals → LLM → fresh queries + trending terms)
   T+5     like 10 niche tweets     (trend-driven queries)
   T+14    PEAK: critic-gated post  (1 thread + og:image, auto-regen if grounding < 7)
           OFF: draft 3 → queue     (your approval needed on /queue)
   T+16    reply  1                 (analyzer picks best of 5 candidates, classifies + styles)
   T+27    reply  2
   T+39    reply  3
   T+51    reply  4
   T+63    reply  5
   T+75    quote-tweet              (viral post, 100–10k likes, under 4h old)
   T+87    conversation follow-ups  (up to 2 — only on non-hostile replies)
   T+110   follow 1                 (60% from followers-of-creator-you-admire)
   T+122   follow 2
   T+134   cycle complete           (sleep ~50 min before next cycle — 2h interval)
```

<sub>All cooldowns are `random.uniform(10, 12)` minutes by default. Adaptive backoff multiplies them x2 / x4 / x8 if X throws errors. Resets on clean cycle.</sub>

<br />

---

<br />

## The intelligence layer

```
   ┌── GitHub ──────────────────────────────────────────────┐
   │   recently-created repos · 8 of 13 AI topics sampled   │
   │   sort by stars · return top 20                        │
   └────────────────────────────────────────────────────────┘
   ┌── HackerNews ──────────────────────────────────────────┐
   │   top 60 stories → AI keyword filter                   │
   └────────────────────────────────────────────────────────┘
   ┌── Reddit ──────────────────────────────────────────────┐
   │   r/LocalLLaMA + r/ChatGPT (anchors) + 2 random of     │
   │   {singularity · MachineLearning · OpenAI · LLMDevs}   │
   └────────────────────────────────────────────────────────┘
   ┌── Newsletters ─────────────────────────────────────────┐
   │   AINews · Latent Space · BensBites · Smol AI ·        │
   │   Import AI  →  recent items via RSS                   │
   └────────────────────────────────────────────────────────┘
   ┌── Creator intel ───────────────────────────────────────┐
   │   for each handle in CREATORS_TO_STUDY:                │
   │   visit profile · scrape top tweets by likes           │
   │   →  live "what's working in this niche" examples      │
   └────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌── trending-term extraction ────────────────────────────┐
   │   regex pulls repo names + capitalised phrases →       │
   │   ['Hermes 3', 'claude-code', 'MCP', 'forkd']          │
   └────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌── niche filter (LLM) ──────────────────────────────────┐
   │   drops crypto/gambling/politics/spam                  │
   │   keeps unfamiliar repo-style names by default         │
   └────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌── LLM strategy brain ──────────────────────────────────┐
   │   3-tier cascade with rate-limit memory:               │
   │     gpt-oss-120b → llama-3.3-70b → gemini-2.5-flash    │
   │   sees:  all signals + memory + trending terms +       │
   │          recent queries + topics covered + repos used  │
   │                                                        │
   │   returns: { reply_queries, like_queries,              │
   │              follow_queries, tweet_topics[],           │
   │              github_repos_to_mention[] }               │
   └────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌── force-inject trending terms ─────────────────────────┐
   │   top 4 extracted terms prepended to reply_queries     │
   │   top 3 prepended to like_queries (deduped)            │
   │   rotates fresh vs recently-used to avoid repetition   │
   └────────────────────────────────────────────────────────┘
                              │
                              ▼
   ┌── pre-flight critic ───────────────────────────────────┐
   │   every draft scored: hook · voice · value · grounding │
   │   score < 7  →  auto-regenerate (up to 3 attempts)     │
   │   grounding < 7  →  hard-cap overall to 6 (fail-safe)  │
   └────────────────────────────────────────────────────────┘
```

<br />

---

<br />

## Stealth & safety

| layer | what it does |
|:------|:---|
| real Chrome | `channel="chrome"` with persistent user-data-dir — X trusts it |
| stealth patches | manual `add_init_script` for `navigator.webdriver`, plugins, WebGL, permissions |
| no `playwright-stealth` | that PyPI package is unmaintained and detected |
| cookie-based login | password never touches disk |
| big random cooldowns | 10–12 min between every major action |
| **account health monitor** | scrapes own profile for suspension/limited warnings each cycle — auto-pauses on critical |
| **adaptive cooldowns** | 2+ errors in a cycle → next cycle x2, then x4, then x8. Resets on clean cycle. |
| **anti-hallucination grounding** | critic auto-fails any tweet that misrepresents a source or omits the URL |
| **cookie refresh detection** | dashboard banner after 30-day cookie age, with one-line re-auth command |
| selector resilience | every action wrapped in try/except + auto-screenshots on failure |
| state persistence | never reposts, never re-replies, never re-follows the same target |
| peak-hour gating | posts only during configurable peak hours; engagement continues off-peak |
| `DRY_RUN` mode | test the full cycle without actually posting |

<br />

---

<br />

## File structure

```
twit-auto/
├── bot/
│   ├── x_automation_bot.py     ◀ main bot
│   ├── intelligence.py         ◀ trend discovery + LLM strategy brain + critic + niche filter
│   ├── creator_intel.py        ◀ creator scraping + content style rotation
│   ├── api_server.py           ◀ FastAPI bridge
│   ├── eval_runner.py          ◀ benchmark prompts/models against tweet_eval.jsonl
│   ├── prompts/
│   │   ├── tweet_prompt.txt
│   │   ├── trend_tweet_prompt.txt
│   │   ├── reply_prompt.txt
│   │   ├── quote_prompt.txt
│   │   ├── follow_up_prompt.txt
│   │   └── style_notes.txt     ◀ YOUR voice — customize this
│   ├── evals/
│   │   ├── tweet_eval.jsonl    ◀ 10 labeled scenarios for the eval harness
│   │   └── last_run.json       ◀ auto-generated
│   └── requirements.txt
├── dashboard/
│   ├── app/
│   │   ├── page.tsx            ◀ /            overview + banners
│   │   ├── memory/page.tsx     ◀ /memory      bot brain + critic log
│   │   ├── queue/page.tsx      ◀ /queue       off-hours draft approval
│   │   ├── analytics/page.tsx  ◀ /analytics   charts + optimal hours
│   │   ├── logs/page.tsx       ◀ /logs        live SSE
│   │   ├── history/page.tsx    ◀ /history     5 tabs
│   │   └── settings/page.tsx   ◀ /settings    LLM cascade picker
│   ├── components/sidebar.tsx
│   ├── lib/api.ts
│   └── package.json
├── launcher.ps1                ◀ silent multi-process launcher
├── stopper.ps1                 ◀ kill-all script
├── .env                        ◀ secrets (gitignored)
└── .env.example
```

<br />

---

<br />

## Configuration

<sub>All in `.env`</sub>

| variable | default | purpose |
|---|---|---|
| `MAX_POSTS_PER_CYCLE`      | `1` | tweets / threads per cycle |
| `MAX_REPLIES_PER_CYCLE`    | `5` | replies — highest growth lever |
| `MAX_QUOTES_PER_CYCLE`     | `1` | quote-tweets per cycle |
| `MAX_FOLLOW_UPS_PER_CYCLE` | `2` | conversation continuations |
| `MAX_LIKES_PER_CYCLE`      | `10` | likes — lowest-risk action |
| `MAX_FOLLOWS_PER_CYCLE`    | `2` | follows — keep low to avoid flag |
| `PEAK_HOURS`            | `9,10,13,14,19,20,21` | when posting is allowed |
| `NICHE`                 | *required* | drives every LLM prompt |
| `X_HANDLE`              | *required* | for self-engagement feedback + health checks |
| `CREATORS_TO_STUDY`     | *empty* | comma-separated X handles (no @) — bot scrapes their tweets each cycle |
| `GROQ_PRIMARY_MODEL`    | `openai/gpt-oss-120b` | tier 1 of the LLM cascade |
| `GROQ_FALLBACK_MODEL`   | `llama-3.3-70b-versatile` | tier 2 — used when tier 1 rate-limits |
| `GEMINI_MODEL`          | `gemini-2.5-flash` | tier 3 — last resort |
| `GROQ_PRIMARY_API_KEY`  | falls back to `GROQ_API_KEY` | own rate budget for tier 1 |
| `GROQ_FALLBACK_API_KEY` | falls back to `GROQ_API_KEY` | own rate budget for tier 2 |
| `DRY_RUN`               | `false` | log actions without performing them |
| `PROXY_URL`             | *empty* | residential proxy for 24/7 use |

<br />

---

<br />

## Tech stack

<div align="center">

| layer | tools |
|:------|:---|
| browser automation | Playwright + real Chrome with persistent profile |
| LLM tier 1 | Groq `openai/gpt-oss-120b` (reasoning + structured JSON) |
| LLM tier 2 | Groq `llama-3.3-70b-versatile` (rate-limit fallback, own API key) |
| LLM tier 3 | Google `gemini-2.5-flash` (last resort, different provider) |
| trend sources | GitHub API · HackerNews · Reddit · 5 AI newsletters · creator profiles |
| backend | FastAPI · Uvicorn · `json-repair` (3-pass LLM JSON recovery) |
| frontend | Next.js 14 · Tailwind · Recharts · SWR · Lucide |
| state | single `bot_state.json` with atomic writes |
| eval | `bot/eval_runner.py` against labeled `tweet_eval.jsonl` |

</div>

<br />

---

<br />

## Troubleshooting

<details>
<summary><b>Dashboard says "offline" after launch</b></summary>
<br />

- Check `logs/launcher.err.log`
- Check `logs/bot.log` and `logs/api.log` for Python tracebacks
- Make sure `python --version` is 3.11+
- Try `Stop Twit-Auto.vbs` → wait 5s → `Start Twit-Auto.vbs`
</details>

<details>
<summary><b>Bot logs say "selector failed"</b></summary>
<br />

X changes its UI periodically. Check `bot/debug_screenshots/` to see what the bot saw at failure time. Update the `SELECTORS` dict at the top of `bot/x_automation_bot.py`.
</details>

<details>
<summary><b>Login flow loops back to the login page</b></summary>
<br />

X blocks Playwright's bundled Chromium. The code uses `channel="chrome"` which loads your real installed Chrome — make sure Google Chrome is installed and reachable.
</details>

<details>
<summary><b>Account suspended</b></summary>
<br />

- Check `bot/x_bot.log` for the rate at which you were posting / following
- Lower `MAX_REPLIES_PER_CYCLE` and `MAX_FOLLOWS_PER_CYCLE` in `.env`
- For the next account, configure a residential `PROXY_URL`
- Wait, appeal, learn
</details>

<br />

---

<br />

## Roadmap

```
   [x]   pre-flight tweet critic (hook + voice + value + grounding)
   [x]   smart reply candidate analyzer (spam/ragebait filter + sentiment)
   [x]   engagement learning loop (top + bottom performer feedback)
   [x]   quote-tweet capability
   [x]   conversation continuation (follow-up on your replies)
   [x]   off-hours draft queue with manual approval
   [x]   reset cycle button (skip cooldowns on demand)
   [x]   creator intelligence (scrape tracked creators for style)
   [x]   content style rotation (6 modes — hook, story, contrarian, listicle, question, comparison)
   [x]   3-tier LLM cascade with per-tier API keys + rate-limit memory
   [x]   anti-hallucination grounding (mandatory source URLs + critic axis)
   [x]   newsletter scrape source (AINews, Latent Space, BensBites, Smol AI, Import AI)
   [x]   image attachment via OG-image extraction
   [x]   followers-of-creator discovery (60% bias toward same-niche audiences)
   [x]   account health monitor (auto-pause on suspension/limit)
   [x]   adaptive cooldowns (1x → 8x backoff on errors)
   [x]   cookie refresh detection (30-day banner)
   [x]   best-time-to-post auto-detect (from your own engagement data)
   [x]   eval harness with adversarial scenarios
   [ ]   real-time engagement tracking per tweet (impressions over time)
   [ ]   multi-account orchestration
   [ ]   DSPy-compiled critic/analyzer prompts
   [ ]   preference-pair logging for future LoRA fine-tuning
```

<sub>PRs welcome.</sub>

<br />

---

<br />

## Disclaimer

This is for **personal / educational growth use**. Respect X's terms. Use conservatively. The defaults are deliberately low because long-term account safety > short-term volume. Don't run this on someone else's account.

<br />

---

<br />

<div align="center">

`╌────────────────────────────────────────────────────────╌`

<br />

**Twitter Growth System · built by [@yuno7777](https://github.com/yuno7777) · MIT**

<sub>*if you ship something cool with this, tag me on X*</sub>

</div>
