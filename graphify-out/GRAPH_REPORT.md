# Graph Report - C:\Users\Abhishek Satarkar\Desktop\projects\twit-auto  (2026-05-23)

## Corpus Check
- Corpus is ~21,288 words - fits in a single context window. You may not need a graph.

## Summary
- 302 nodes · 518 edges · 27 communities (23 shown, 4 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 13 edges (avg confidence: 0.89)
- Token cost: 10,600 input · 3,000 output

## Community Hubs (Navigation)
- [[_COMMUNITY_API Server & Endpoints|API Server & Endpoints]]
- [[_COMMUNITY_Dashboard Dependencies|Dashboard Dependencies]]
- [[_COMMUNITY_AI Strategy & News Ingestion|AI Strategy & News Ingestion]]
- [[_COMMUNITY_LLM Generation & Critic Gate|LLM Generation & Critic Gate]]
- [[_COMMUNITY_Dashboard TSConfig|Dashboard TSConfig]]
- [[_COMMUNITY_Frontend API Clients|Frontend API Clients]]
- [[_COMMUNITY_Bot Execution Loop|Bot Execution Loop]]
- [[_COMMUNITY_Browser Stealth & Auth|Browser Stealth & Auth]]
- [[_COMMUNITY_Frontend Pages & UI Utils|Frontend Pages & UI Utils]]
- [[_COMMUNITY_Browser Automation Interactions|Browser Automation Interactions]]
- [[_COMMUNITY_Prompt Templates & Guidelines|Prompt Templates & Guidelines]]
- [[_COMMUNITY_History Frontend Pages|History Frontend Pages]]
- [[_COMMUNITY_Overview Page & Stats|Overview Page & Stats]]
- [[_COMMUNITY_Dashboard Shell & Layout|Dashboard Shell & Layout]]
- [[_COMMUNITY_Interaction Targeting|Interaction Targeting]]
- [[_COMMUNITY_Analytics Pages|Analytics Pages]]
- [[_COMMUNITY_CLI Metadata & Resources|CLI Metadata & Resources]]
- [[_COMMUNITY_Settings Frontend Page|Settings Frontend Page]]
- [[_COMMUNITY_Browser Safety Checks|Browser Safety Checks]]
- [[_COMMUNITY_Next.js Configuration|Next.js Configuration]]
- [[_COMMUNITY_Tailwind CSS Configuration|Tailwind CSS Configuration]]
- [[_COMMUNITY_Agent Workflow Documentation|Agent Workflow Documentation]]

## God Nodes (most connected - your core abstractions)
1. `run_cycle()` - 34 edges
2. `json()` - 20 edges
3. `read_state()` - 18 edges
4. `compilerOptions` - 16 edges
5. `jitter()` - 14 edges
6. `cn()` - 13 edges
7. `save_state()` - 12 edges
8. `synthesize_strategy()` - 11 edges
9. `call_llm()` - 11 edges
10. `main_loop()` - 9 edges

## Surprising Connections (you probably didn't know these)
- `_validate_strategy()` --calls--> `next`  [INFERRED]
  bot/intelligence.py → dashboard/package.json
- `run_cycle()` --calls--> `next`  [INFERRED]
  bot/x_automation_bot.py → dashboard/package.json
- `Builder-centric Voice Guidelines` --conceptually_related_to--> `Engagement Learning Loop`  [INFERRED]
  bot/prompts/style_notes.txt → README.md
- `cn()` --calls--> `clsx`  [INFERRED]
  dashboard/lib/utils.ts → dashboard/package.json
- `SummaryCard()` --calls--> `cn()`  [EXTRACTED]
  dashboard/app/analytics/page.tsx → dashboard/lib/utils.ts

## Hyperedges (group relationships)
- **LLM Generation Prompts Suite** — follow_up_prompt, quote_prompt, reply_prompt, trend_tweet_prompt, tweet_prompt [INFERRED 0.95]
- **Bot Anti-Detection & Safety Layer** — readme_concept_real_chrome, readme_concept_random_cooldowns, readme_concept_critic_gate [INFERRED 0.95]
- **User Alignment and Quality Optimization Loop** — readme_concept_engagement_loop, readme_concept_critic_gate, style_notes_concept_style_notes_voice [INFERRED 0.95]

## Communities (27 total, 4 thin omitted)

### Community 0 - "API Server & Endpoints"
Cohesion: 0.10
Nodes (28): BaseModel, analytics(), approve_draft(), control(), ControlBody, critic_log(), DraftActionBody, edit_draft() (+20 more)

### Community 1 - "Dashboard Dependencies"
Cohesion: 0.06
Nodes (30): dependencies, class-variance-authority, lucide-react, next, @radix-ui/react-slot, @radix-ui/react-tabs, react, react-dom (+22 more)

### Community 2 - "AI Strategy & News Ingestion"
Cohesion: 0.12
Nodes (24): analyze_reply_candidates(), _build_strategy_prompt(), critique_text(), _default_strategy(), _extract_json(), extract_trending_terms(), fetch_github_recent_hot(), fetch_hackernews_ai() (+16 more)

### Community 3 - "LLM Generation & Critic Gate"
Cohesion: 0.16
Nodes (22): call_llm(), _configure_gemini(), format_top_tweets(), _gate_with_critic(), generate_follow_up(), generate_quote(), generate_reply(), generate_thread() (+14 more)

### Community 4 - "Dashboard TSConfig"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 5 - "Frontend API Clients"
Cohesion: 0.19
Nodes (19): approveDraft(), BotStatus, editDraft(), getAnalytics(), getBotStatus(), getCriticLog(), getFollowHistory(), getFollowUpHistory() (+11 more)

### Community 6 - "Bot Execution Loop"
Cohesion: 0.20
Nodes (18): check_control_flag(), check_force_new_cycle(), consume_force_new_cycle(), like_recent_tweets(), load_state(), long_wait(), main_loop(), Read just the status field from state — cheap polling for pause/stop. (+10 more)

### Community 7 - "Browser Stealth & Auth"
Cohesion: 0.16
Nodes (16): apply_stealth_patches(), cli(), _dedupe_keep_order(), discover_user_candidates(), fetch_news(), in_peak_hour(), launch_browser(), login_flow() (+8 more)

### Community 8 - "Frontend Pages & UI Utils"
Cohesion: 0.22
Nodes (11): OverviewPage(), clsx, CriticEntry, DraftItem, MemoryResponse, cn(), formatLocalTime(), timeAgo() (+3 more)

### Community 9 - "Browser Automation Interactions"
Cohesion: 0.23
Nodes (14): follow_user(), human_type(), jitter(), post_follow_up_reply(), post_quote_tweet(), post_reply(), post_thread(), post_tweet() (+6 more)

### Community 10 - "Prompt Templates & Guidelines"
Cohesion: 0.21
Nodes (13): bot/prompts/follow_up_prompt.txt, bot/prompts/quote_prompt.txt, Pre-Flight Tweet Critic Scoring, Engagement Learning Loop, Randomized Cooldown Intervals, Real Chrome Browser Channel Setup, Reply Candidate Analyzer, bot/prompts/reply_prompt.txt (+5 more)

### Community 11 - "History Frontend Pages"
Cohesion: 0.15
Nodes (4): Tab, TABS, FollowUpHistoryItem, QuoteHistoryItem

### Community 12 - "Overview Page & Stats"
Cohesion: 0.22
Nodes (7): handleControl(), statusStyle, controlBot(), FollowHistoryItem, ReplyHistoryItem, StatsResponse, TweetHistoryItem

### Community 13 - "Dashboard Shell & Layout"
Cohesion: 0.29
Nodes (5): metadata, dot, nav, Sidebar(), StatusResponse

### Community 14 - "Interaction Targeting"
Cohesion: 0.29
Nodes (7): discover_quote_candidates(), discover_reply_candidates(), _parse_count(), Visit own profile, scrape recent tweets + like counts, store top 5 in state.top_, Find VIRAL fresh tweets to quote-tweet. Different filter than reply: high likes., scrape_own_top_tweets(), TweetCandidate

### Community 15 - "Analytics Pages"
Cohesion: 0.33
Nodes (3): RANGES, SummaryCard(), AnalyticsResponse

### Community 16 - "CLI Metadata & Resources"
Cohesion: 0.40
Nodes (4): id, name, projectResources, resources

### Community 18 - "Browser Safety Checks"
Cohesion: 0.50
Nodes (4): Wrap a Playwright coroutine; on failure, take a screenshot and return None., Verify compose tweet button is visible — indicates UI is intact., safe_action(), selector_health_check()

## Knowledge Gaps
- **60 isolated node(s):** `id`, `name`, `resources`, `nextConfig`, `name` (+55 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `dependencies` connect `Dashboard Dependencies` to `Frontend Pages & UI Utils`?**
  _High betweenness centrality (0.308) - this node is a cross-community bridge._
- **Why does `next` connect `Dashboard Dependencies` to `AI Strategy & News Ingestion`, `Bot Execution Loop`?**
  _High betweenness centrality (0.299) - this node is a cross-community bridge._
- **Why does `run_cycle()` connect `Bot Execution Loop` to `Dashboard Dependencies`, `LLM Generation & Critic Gate`, `Browser Stealth & Auth`, `Browser Automation Interactions`, `Interaction Targeting`, `Browser Safety Checks`?**
  _High betweenness centrality (0.250) - this node is a cross-community bridge._
- **What connects `id`, `name`, `resources` to the rest of the system?**
  _105 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `API Server & Endpoints` be split into smaller, more focused modules?**
  _Cohesion score 0.09982174688057041 - nodes in this community are weakly interconnected._
- **Should `Dashboard Dependencies` be split into smaller, more focused modules?**
  _Cohesion score 0.06451612903225806 - nodes in this community are weakly interconnected._
- **Should `AI Strategy & News Ingestion` be split into smaller, more focused modules?**
  _Cohesion score 0.12333333333333334 - nodes in this community are weakly interconnected._