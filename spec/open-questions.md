# Open product questions

New product questions continue the handoff numbering (Q204+), per ADR-031. Each has the question, a recommended
answer, the reason and — once given — the owner's final decision, which then becomes the next ADR the same turn.

Status legend: **OPEN** (needs the owner) · **LEGAL** (needs a legal/compliance answer, not an owner preference) ·
**DECIDED → ADR-###**.

## Found at import (2026-09-28): conflicts and gaps between the locked decisions

### Q204 — OPEN — One shared market-data feed vs each user's own Zerodha data (conflict)
- **Conflict.** ADR-012 (Q105, Q107, §84): one shared provider stream, fanned out to all users; never one vendor
  connection per user. ADR-014 (Q175, §39): the interim V1 data source is Zerodha live data, with each user guided
  to connect Zerodha. Serving one Zerodha account's data to many users is redistribution, which §39 and Q178 say must
  not be assumed. With per-user Zerodha data, there is no shared feed.
- **Example.** 5,000 users all watching the NIFTY chain: shared model = 1 feed; per-user model = 5,000 Zerodha
  connections, each only allowed to show its own user's screen.
- **Options.** (a) Each user's own Zerodha session feeds only that user's screens until a licensed vendor exists;
  shared calculations are shared only where they do not redistribute data. (b) One platform Zerodha feed shared by
  all users — only with Zerodha's written permission. (c) Sign a licensed NSE+BSE vendor before launch.
- **Recommended:** (a) for V1, plus a written question to Zerodha. It is the only option that is legal today
  without a contract we don't have. **Cost:** (a) loses the scale saving of ADR-012 until a vendor is signed.
- Spec basis: ADR-012, ADR-014; handoff §38, §39, §84, Q105, Q175, Q178.

### Q205 — OPEN — Monitoring and alerts when the user's Zerodha session has expired
- **Gap.** Zerodha authorization lasts ~1 day (ADR-020). Monitoring, reconciliation and exit alerts for active
  strategies (ADR-010, ADR-018, Q89) need live data and broker state. Under the interim Zerodha data source, a user
  who has not logged in today has no data feeding their strategy.
- **Example.** A user's Iron Condor is active; they don't log in on Monday; NIFTY falls 400 points at 11:00. With
  no valid session the platform cannot see the move or the positions, so no Red "exit condition" alert fires.
- **Recommended:** show the strategy as "Monitoring paused — reconnect Zerodha" and send a morning reconnect
  reminder, until a licensed vendor feed (which doesn't depend on the user's session) exists. Say so plainly in the
  product, because users will assume monitoring is continuous.
- Spec basis: ADR-010, ADR-018, ADR-020, ADR-023 (Q89); state "Monitoring Paused" already exists in Q200.

### Q206 — OPEN — Price source for drafts and trials without Zerodha
- **Gap.** Drafts are allowed without Zerodha (Q185–Q186) and the trial starts at registration (Q88), but the only
  interim price source is Zerodha. Payoff and scenario numbers need entry prices.
- **Options.** (a) User types the prices; the draft is marked "manual prices". (b) Show sample/static data labelled
  Sample · Not Live (as Q92 allows for the chain). (c) Require Zerodha to see any prices.
- **Recommended:** (a) + (b). The draft stays useful without breaking the "no live data without login/licence" rules.
- Spec basis: ADR-020, ADR-023; Q58, Q88, Q92, Q185–Q188.

### Q207 — OPEN — Futures leg payoff formula
- **Gap.** Futures Buy/Sell are V1 leg types (ADR-001) but the locked formulas cover options only.
- **Recommended:** BUY FUT `(Market − Entry Price) × Quantity`; SELL FUT `(Entry Price − Market) × Quantity`, at
  expiry and live (with LTP for live). Standard futures payoff; it needs the owner's OK only because formulas are
  locked.
- Spec basis: ADR-008, `spec/business-rules/scenario-calculations.md` §1.

### Q208 — OPEN — Scenario and range-picker step for SENSEX
- **Gap.** The 100-point step is stated for NIFTY ("NIFTY-style examples"). SENSEX trades at roughly three times
  NIFTY's level (index levels not re-measured today), so 100 points on SENSEX is a much smaller move.
- **Recommended:** store the step per underlying as configuration; start SENSEX at a step giving a similar number
  of columns over a similar % range (e.g. 300 points). Needs real SENSEX strike spacing checked from the instrument
  master before choosing.
- Spec basis: ADR-005 (Q130), ADR-008 (Q120).

### Q209 — OPEN — How a referral's success reaches the platform
- **Gap.** Q61 rewards a referral only when a Zerodha account is actually opened and attributed to the user. No
  mechanism is recorded for how the platform learns this (no Zerodha referral API is known; unverified).
- **Recommended:** admin imports confirmed referral openings (CSV, same tooling as ADR-024), each creating an
  entitlement event with its reference. Automate later if Zerodha offers a feed.
- Spec basis: ADR-024, ADR-025.

### Q210 — OPEN — How each user connects Zerodha, and what it costs them
- **Gap.** §39 says "guide users step-by-step to connect Zerodha APIs". That could mean each user creates their own
  Kite Connect developer app (and pays Zerodha's API fee themselves), or that the platform registers one app and each
  user just logs in through it. These are very different products (setup friction and a monthly fee vs a one-click
  login). Zerodha's current fees and terms are **not verified** here.
- **Recommended:** one platform app with per-user login, if Zerodha's terms allow it for a multi-user SaaS; verify
  from current Kite Connect terms before deciding.
- Spec basis: ADR-014 (Q175, Q176), ADR-020.

### Q211 — LEGAL — Compliance review before these features go live
Already required by the handoff (§2, §70, Q158); listed here so it has an owner and a gate:
strategy discovery and strike "Suggested setup"; adjustment approaches; notification content; a paid subscription
sold by a registered Zerodha Authorised Person; market-data redistribution; Zerodha API terms; retention of the
anti-abuse record after account deletion (Q96, India's DPDP Act). **Nothing here is a conclusion** — no legal
research was done at import. Gate: these features stay out of production until the review is recorded.

## Carried over, never answered

### Q33A — OPEN — What the scenario columns show (15 Sep handoff §38)
A. Expiry P&L only · B. Estimated current P&L only · C. Both, expiry as default. ChatGPT recommended **C**. The later
handoffs skipped it; the comprehensive handoff lists it as open ("exact current-vs-expiry P&L model"). Until
answered, the table shows expiry P&L only (the only locked formulas). **Recommended:** C, because live management
needs the current estimate, but the estimate needs pricing assumptions (IV, time value) that are themselves open.

### Q81 — OPEN (confirm) — Home dashboard layout
Every handoff calls the Home layout in ADR-027 *proposed*; the Latest handoff says to confirm it; no answer is
recorded. The direction is already locked (Chat1: "simple, action-oriented home screen, not a trading terminal"
= B); only the exact layout is unconfirmed. **Recommended:** accept it as written.

## Open areas listed by the handoff (§95) — to become Q-numbers only when work needs them
Exact production market-data vendor and licensing · Zerodha commercial approval for SaaS data use · historical
provider · live-estimate P&L model · option pricing/IV/time-value assumptions · bid/ask/slippage · charges model ·
order types and per-leg pricing UX · tick rounding · timeout/cancel/repricing · MIS/NRML · expiry/multi-expiry
execution edge cases · quantity edge cases · existing-position grouping algorithm · alert provider, consent, quiet
hours, templates, escalation, dedupe, rate limits · adjustment rule priority/conflict/cooldown · detailed security
architecture · data-retention policy · SEBI/legal outcomes · admin/system-health screens · final cloud/stack · the
strategy state transition table (drafted in `spec/data/domain-model.md`) · what happens when a Client ID is
removed from the complimentary list (ADR-024).
