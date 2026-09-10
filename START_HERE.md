# START HERE — freelance setup checklist

Work top to bottom. Sitting 1 and 2 are one-time. Sitting 3 is the daily loop.

Companion docs: [FREELANCE_KIT.md](FREELANCE_KIT.md) (profile copy, proposal
templates, rates) · [X_THREAD.md](X_THREAD.md) (the thread to post) ·
[PORTFOLIO_CASE_STUDY.html](PORTFOLIO_CASE_STUDY.html) (your portfolio piece).

---

## SITTING 1 — secure & publish the code (~45 min)

- [ ] **Rotate the exposed Jupiter key.** Go to https://portal.jup.ag → API
      keys → revoke the old key → create a new one → store it in a password
      manager. (The old key is sitting in a filename in the `Trade Bot`
      folder — treat it as burned.)
- [ ] **If the wallet in `.env` still holds SOL:** move it out to another
      wallet now. Copy the `.env` values somewhere safe if you still need
      them, then:
- [ ] **Clean the original folder:**
      ```bash
      cd ~/Downloads/"Trade Bot"
      rm -f .env .env.example .envJUPITER_API_KEY=*
      ```
- [ ] **Commit the clean repo:**
      ```bash
      cd ~/Downloads/trade-bot-portfolio
      git init
      git add .
      git commit -m "Trade Bot: multi-strategy crypto trading system (post-mortem)"
      ```
- [ ] **Push to GitHub:**
      - Have `gh`: `gh repo create trade-bot --public --source=. --push`
      - No `gh`: github.com → **New repository** → name `trade-bot`, Public,
        add nothing → run the "push an existing repository" lines it shows.
- [ ] Paste the repo URL back to Claude to wire it into the kit, thread, and
      case study.

---

## SITTING 2 — profiles (~90 min)

- [ ] **Publish the case study.** Open the artifact
      (https://claude.ai/code/artifact/b3be13b0-ffb1-4509-ab24-31762fb657f9)
      → **Share** (top right) → anyone-with-link → copy the URL. This is your
      portfolio link everywhere.
- [ ] **Upwork** (upwork.com → sign up as a freelancer):
  - [ ] Title, Overview, Skills → paste from FREELANCE_KIT.md §5
  - [ ] Hourly rate → **$48**
  - [ ] Add 1 Portfolio item: title "Multi-strategy crypto trading system",
        body = the "proof point" paragraph from §1, link case study + repo
  - [ ] Fill employment/education briefly and honestly
  - [ ] Start **ID verification** now (ID photo + selfie; ~1 day to approve)
- [ ] **Contra** (contra.so): headline + blurb from §5, link the case study
- [ ] **X/Twitter:**
  - [ ] Bio → the one-liner from §5
  - [ ] Post the thread from X_THREAD.md (swap in the case study + repo links)
  - [ ] Pin the thread

---

## SITTING 3 — proposals (~60 min, then repeat every morning)

- [ ] Upwork → **Find Work** → search: `python automation`, `api integration`,
      `web scraping`, `discord bot`, `solana`, `websocket`
- [ ] Filters: **posted last 24 hours**, **payment verified** clients only
- [ ] Pick **4** jobs you could genuinely do
- [ ] For each (~12 min): open the matching template in FREELANCE_KIT.md §6 →
      rewrite the first line to name *their* specific problem → keep under
      120 words → link the case study only if relevant → send
- [ ] Log each in a sheet: `date | job title | client | budget | status`
- [ ] Reply to any client message the **same day**
- [ ] **Repeat steps 1–6 every morning.** This is the job until you're booked.

---

## Rules that keep it on track

- Raise your rate every 2–3 completed jobs until replies slow, then hold.
- Scope in writing before starting. 30–50% paid up front. Don't send final
  code before final payment clears.
- Never hold client funds or private keys. You build the tool; they run it.
- Never promise a profitable strategy — only "I'll build what you spec and
  show it works on historical data."
- Run salaried remote job applications in parallel with the same portfolio.

---

## Rough timeline

| when | expect |
|---|---|
| Week 1–4 | first small contract; rate $45–55/hr; lots of silence — normal |
| Month 2–3 | 3–5 reviews; rate $60–85/hr; ~$2–5k/mo if you keep sending |
| Month 4–6+ | 1–2 repeat clients; rate $80–120/hr; $5–10k/mo if booked |
