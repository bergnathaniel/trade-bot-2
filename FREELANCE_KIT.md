# Freelance / Contract Kit

Turning the Trade Bot build into paid work. The trading had no edge; the
engineering is the product now. This file is the playbook — profile copy to
paste, proposal templates to adapt, a two‑week plan to work through.

Resolved: market **US**, email **naberg30@gmail.com**, availability **30+
hrs/wk**, case study **https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9**
(private until you share it from the page's share menu).

Still to fill: your **name** (written as **Nathaniel Berg** throughout —
correct if wrong) and `[GITHUB]` (your handle, once the cleaned repo is
pushed).

---

## 1. The pitch

**One‑liner**
> Python engineer for real‑time data systems — I build the pipes that ingest
> messy live data from flaky third‑party APIs and act on it reliably.

**Two sentences (bios, intros)**
> I build backend systems that consume live data — websockets, filtered
> streams, webhooks — normalise it, and drive decisions off it in under a
> second. Recent work: a six‑strategy crypto trading stack on Solana with a
> backtester that runs the production code, an eight‑check on‑chain fraud
> screen, and a layered risk framework — ~9k lines, four dependencies.

**The proof point (lead with this everywhere)**
A multi‑strategy automated trading system: async multi‑source ingestion
(Helius `logsSubscribe`, X API v2 filtered stream, pump.fun migration feed,
local webhook) fused on one queue; on‑chain analysis reading token accounts
for authority state, holder concentration and liquidity forensics; a
backtester with train/test discipline that disproved its own strategies
before real money moved. Case study: `https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9`.

The honesty *is* the selling point — you ran a real experiment, measured it
against buy‑and‑hold, and called the result instead of tuning forever. Say
that out loud. Clients hiring for data work want someone who reports what the
data says.

---

## 2. What you're selling — five service lines, ranked by how winnable they are

1. **Python automation & API integration** *(highest volume, lowest bar,
   fastest first review)*
   "Connect X to Y", scrape/extract, scheduled jobs, clean up a script that
   breaks weekly, wrap a service in a small API. You've done the hard version
   of this — undocumented, rate‑limited, schema‑drifting APIs verified against
   live traffic.

2. **Real‑time data pipelines / backend workers** *(your strongest
   differentiated skill)*
   Websocket consumers, streaming ingestion, queue workers, webhook
   endpoints, dedupe/fusion, backpressure, reconnect logic. Fewer people can
   actually do this well; it pays more.

3. **Crypto / on‑chain data & bots** *(hot niche, clients with budget, few
   devs who know the tooling)*
   Wallet tracking, token screening, Telegram/Discord bots for trading
   communities, Jupiter / Helius / RPC integration, "build me a bot that does
   X" (they take the market risk, you build the plumbing). Your Solana
   tooling knowledge is worth real money here even though your own trades
   lost — clients want the pipes.

4. **Backtesting & quant tooling** *(steady niche demand)*
   Build a backtest harness, implement a strategy from someone's spec, clean
   market data for a researcher, add cost/slippage modelling, enforce
   out‑of‑sample splits. r/algotrading and Upwork are full of "backtest my
   idea" jobs.

5. **Data dashboards & reporting** *(small, pairs well with 1–2)*
   You have `dashboard.py` + a template. Good add‑on, weak as a headline.

**Say no to:** anything where you'd hold client funds or private keys, manage
someone's live trading capital, or promise a profitable strategy. Build the
tool, hand it over, they run it. Put that in writing (see §10).

---

## 3. Rates

Calibrated for billing from the **US**. Numbers below are USD.

| Stage | Hourly (Upwork) | Hourly (direct / Contra) |
|---|---|---|
| First 2–3 jobs (buying reviews) | $35–50 | $50–70 |
| After ~3 five‑star reviews | $60–85 | $75–100 |
| Established in the crypto/RT niche | $90–140 | $110–160 |

**Fixed‑price jobs:** estimate hours honestly, multiply by your target
hourly, add 30% buffer, quote that as one number. Never quote hourly on a
small well‑scoped job — you eat the overruns and the client fears an open
meter.

**Rules**
- Milestone payments, always. 30–50% up front on fixed work. Upwork
  Escrow / milestones on platform.
- The case study lets you skip the $15/hr basement. Don't apologise for
  $50/hr with a portfolio like that.
- Raise your rate every 2–3 completed jobs until proposals stop converting,
  then hold.

---

## 4. Where to find work

**Platforms**
- **Upwork** — biggest volume, most competition, 10% fee. Worth it purely
  for review velocity in month 1. Send 3–5 *tailored* proposals/day, not 20
  copy‑pastes. Use "Rising Talent" filters, apply within an hour of a job
  posting.
- **Contra** — 0% commission, direct clients, less volume. Good once you
  have the case study to link.
- **Braintrust** — no talent fee, enterprise clients, screening to pass.
  Higher rates. Apply once the profile is polished.
- **Wellfound (AngelList)** — startup contract + full‑time. Set to "open to
  contract", filter remote.
- **Fiverr** — only for *productized* offers (see below). Not for hourly.
- **Toptal / Gun.io** — hard screen, top rates. A month‑2 move.

**Niche channels (often better clients, less bidding war)**
- **X/Twitter** — this niche hires off Twitter constantly. Post the case
  study as a thread, put "building real‑time data systems · open to contract"
  in your bio, reply usefully in build‑in‑public / Solana dev threads.
- **r/forhire** (as "[HIRING]"‑hunter and a monthly "[FORHIRE]" post),
  **r/algotrading**, **r/pygame**‑style project subs, **r/juststart**.
- **Web3 boards** — cryptojobslist.com, web3.career, remote3.co,
  cryptocurrencyjobs.co. Filter "contract" / "part‑time".
- **QuantConnect forum**, **QuantStart**, algotrading Discords — "strategy
  implementation" and "data plumbing" requests.
- **Telegram/Discord trading communities** — they constantly want bots and
  dashboards; lurk, be helpful, mention you build them.

**Productized offers (Fiverr / Contra / a simple landing page)**
- "I will build a Solana price / alert Telegram bot" — $150–400
- "I will build a custom backtest for your trading strategy" — $250–600
- "I will build a Python script to pull and clean data from any API" —
  $80–250
- "I will build a real‑time webhook → action pipeline" — $300–800

---

## 5. Profile copy (paste‑ready)

### Upwork — Title (70 char max)
```
Python Dev — Real-Time Data Pipelines, APIs, Crypto/On-Chain Bots
```

### Upwork — Overview
```
I build Python backends that ingest live data from messy third-party APIs
and act on it reliably — websockets, filtered streams, webhooks, queue
workers, scheduled jobs.

Recent project: a six-strategy automated crypto trading system on Solana.
- Async multi-source ingestion (Helius logsSubscribe websockets, X API v2
  filtered stream, a migration feed, a local webhook) fused and de-duplicated
  on one queue, signal-to-decision under a second.
- On-chain analysis: reading token accounts for mint/freeze authority,
  holder concentration, liquidity drain, honeypot-shaped price impact — a
  graded fraud screen with explicit handling of unverifiable data.
- A backtester that replays the real production code over historical data
  with a cost/slippage model and a strict in-sample/out-of-sample split.
- Layered risk controls: bankroll caps, a daily-loss circuit breaker,
  slippage guards, fail-closed defaults, every skipped decision logged.
~9,000 lines of Python, four third-party dependencies. Full write-up:
https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9

What I do well:
- Integrating undocumented, rate-limited, fast-changing APIs (verify schemas
  against live traffic, handle the reconnects and the 429s)
- Real-time / streaming systems and webhook handlers
- Backtesting and simulation tooling for trading strategies
- Data extraction, cleaning, and dashboards
- Minimal-dependency, well-logged, auditable code

I don't take on managing live trading capital or holding keys/funds — I
build the tool and hand it over. Happy to start with a small paid test task.
```

### Upwork — Skills
`Python · asyncio · WebSockets · REST APIs · Web Scraping · Data Pipeline ·
ETL · Solana · Web3 · Trading Bots · Backtesting · pandas · Automation ·
Telegram Bot · Webhooks`

### Contra / personal site — headline + blurb
```
Nathaniel Berg — Python engineer, real-time data systems

I build the backend that consumes live data and acts on it: websocket
ingestion, multi-source fusion, webhook pipelines, backtesting and
simulation infrastructure, on-chain analytics on Solana. Recently built a
six-strategy trading stack with a backtester that runs the production code
and an eight-check on-chain fraud screen — https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9.

Open to contract work, ~30+ hrs/week. naberg30@gmail.com
```

### Wellfound — one-liner
```
Python engineer specialising in real-time data pipelines, API integration,
and on-chain/crypto tooling. Open to remote contract.
```

### X/Twitter bio
```
Python · real-time data systems, API plumbing, on-chain tooling · built a
6-strategy trading stack & wrote the honest post-mortem · open to contract
```

### Job-board blurb (cryptojobslist etc., 1–2 lines)
```
Python dev for real-time & on-chain data work — websocket ingestion, Helius
/ Jupiter / RPC integration, trading-bot plumbing, backtesting. Portfolio:
https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9
```

---

## 6. Proposal templates

Rules: first line names their problem, second line is your relevant proof,
third is one specific question, close with a small next step. No "Dear
Hiring Manager", no autobiography. 120 words max. Attach/link the case study
only when relevant.

### A — Python automation / API integration
```
Hi — you need [restate the job: e.g. "a script that pulls orders from the
Shopify API daily and pushes them to a Google Sheet, without breaking when
the API changes"]. I do exactly this kind of integration work; my last
project ran against four undocumented, rate-limited APIs and stayed up by
verifying schemas against live traffic and handling the ret/429 cases
properly.

One question: is [X — e.g. "the Sheet the single source of truth, or does
data flow back the other way too"]? That changes the design.

I can do a fixed price once scope is clear, or start with a small paid task
so you can see how I work. Code samples: [GITHUB]
```

### B — Real-time / streaming / webhook backend
```
Hi — this is a real-time ingestion problem: [restate, e.g. "consume a
websocket feed, dedupe, and fire a webhook within a second of a matching
event"]. That's the core of what I just built — multiple live sources
(websockets, a filtered stream, webhooks) normalised onto one async queue
with de-duplication and sub-second latency to action. Write-up:
https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9

Question: what's your latency budget end to end, and what happens on a
missed/duplicate event — drop, or replay?

Suggested start: a paid spike to stand up the ingestion + one end-to-end
path, then scope the rest from there.
```

### C — Crypto / on-chain / trading bot
```
Hi — you want [restate: e.g. "a Telegram bot that alerts on new Solana
tokens passing a liquidity/holder filter"]. I built a six-strategy Solana
trading system this year: Helius websockets + Jupiter APIs, an on-chain rug
screen (authority state, holder concentration, LP status, honeypot probe),
and a backtester over real historical data. Full honest post-mortem —
including where the strategies failed — here: https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9

To scope it: which chain(s), and do you have a data source in mind (Helius,
Birdeye, raw RPC) or should I pick?

I build and hand over the tool — I don't manage funds or hold keys. Fixed
price once scope is set; can start on a paid milestone this week.
```

---

## 7. Portfolio prep

### 7a. The case study — `PORTFOLIO_CASE_STUDY.html`
Already written and strong. To ship it:
- Fill the contact block: `[ your email ]`, `[ repo link ]`, `[ portfolio ]`.
- Publish it somewhere with a stable URL — GitHub Pages, Netlify drop,
  Cloudflare Pages, or as a Claude Artifact. That URL becomes
  `https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9` everywhere above.
- Link it from every profile.

### 7b. Make the code repo publishable — do this BEFORE `git init`

This folder is **not a git repo yet** — good, nothing has leaked. Before it
becomes one:

**Secrets to remove from the folder (not just gitignore):**
- `.env` — contains `SOLANA_PRIVATE_KEY`, `HELIUS_RPC_URL` (has an api-key),
  `JUPITER_API_KEY`. Keep it out of git forever.
- `.envJUPITER_API_KEY=jup_...` — a real Jupiter key sitting **in a
  filename**. Delete it, and **rotate that key** at portal.jup.ag — assume
  it's burned.
- Regenerate the **Helius** api-key too if that URL ever landed in a log or
  `.out` file (grep below).
- If the `SOLANA_PRIVATE_KEY` wallet still holds anything, move the funds;
  never reuse that key in a public context.

**Scan before publishing:**
```bash
grep -rnE '(jup_[A-Za-z0-9]{20,}|api-key=|-----BEGIN|[1-9A-HJ-NP-Za-km-z]{80,})' \
  --include='*.py' --include='*.md' --include='*.html' --include='*.csv' --include='*.log' .
```
(Source is currently clean; logs/CSVs are not checked yet.)

**Expand `.gitignore` before the first commit:**
```
.env*
*.log
*.out
*.csv
*_state.json
live_state.json
.mu_cache_*.json
*.bak
*.PRE_*
__pycache__/
*.pyc
.DS_Store
```

**Better: publish a curated repo, not the working directory.** ~40 files
and 100+ logs/caches read as scratch. A hiring client skims. Keep a tight
set that shows range:
- `alpha_bot.py`, `signal_sources.py` — real-time multi-source ingestion
- `rug_screen.py` — on-chain fraud heuristics
- `newcoin_backtest.py`, `momentum_basket.py` — backtesting with train/test
- `executors.py`, `wallet.py` — Jupiter swaps, stdlib key derivation
- `newcoin_model.py` — hand-rolled logistic regression
- `dashboard.py` + `dashboard.html`
- `README.md`, `PORTFOLIO_CASE_STUDY.html`, `requirements.txt`,
  `.env.example`
Drop the logs, caches, `*_state.json`, `*.bak`, `*.PRE_*`, and the
half-finished experiments. Add a 3-line "what's here" note to the README top.

---

## 8. First 14 days

**Days 1–2 — assets**
- [ ] Rotate the Jupiter key; move any wallet funds; delete `.env*` +
      key-in-filename file from the folder
- [ ] Build the curated portfolio repo, push to `[GITHUB]`
- [ ] Fill case-study contact block; publish it; capture `https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9`

**Days 3–4 — profiles**
- [ ] Upwork profile (copy from §5), ID verification, set rate $45–50/hr
- [ ] Contra profile + link case study
- [ ] One niche board (cryptojobslist or web3.career)
- [ ] X bio update + draft the case-study thread

**Days 5–14 — outreach**
- [ ] Post the X thread; pin it
- [ ] 3–5 tailored Upwork proposals/day (templates §6), logged in a sheet
- [ ] 1 monthly r/forhire post + reply to 2–3 [HIRING] posts/day
- [ ] 2 productized listings (Fiverr or Contra) from §4
- [ ] Reply usefully in 1–2 Solana-dev / algotrading threads per day
- [ ] Review conversion at day 14: if <5% reply rate, tighten the first
      line of proposals and lower rate one notch; if >20%, raise the rate

**Target:** first signed milestone within 14 days, first 5-star review within
30.

---

## 9. Pipeline tracking

One sheet, six columns: `date · source · role · rate/budget · proposal sent
(y/n) · status`. Status flow: `sent → replied → call → proposal → won/lost`.
Review weekly: which source and which template convert. Kill what doesn't.

---

## 10. Guardrails (put these in every contract/scope doc)

- **No funds, no keys.** You build and deliver the tool; the client runs it
  with their own credentials and capital. State it in the proposal and the
  contract.
- **No profit promises.** "I'll build the strategy/bot you specify and show
  it works against historical data" — never "this will make money."
- **Scope in writing** before work starts: deliverables, what's explicitly
  out, revision count, definition of done.
- **Milestones + partial payment up front.** Don't deliver the final code
  before the final payment clears.
- **Your code, licensed on payment.** Keep the right to reuse generic
  components (a websocket client, a backtest scaffold) across clients.
- **Hours cap on hourly work**; flag at 80% of estimate, never blow past
  silently.
```
