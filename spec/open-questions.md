# Open product questions

New product questions continue the chats' numbering (Q204+), per ADR-031. Each has the question, a recommended
answer, the reason and — once given — the owner's final decision, which then becomes the next ADR the same turn.
Updated 2026-09-28 after reading both full ChatGPT chats (`spec/traceability/question-register.md`).

Status: **OPEN** (needs the owner) · **LEGAL** (needs a legal/compliance answer) · **EXTERNAL** (waiting on a third
party) · **DECIDED → ADR-###**.

## Closed by the full chats (were open after the handoff import)
- **Q33A** — DECIDED: C, both views, Expiry P&L default (T1 #111) → ADR-008.
- **Q81** — DECIDED: C, hybrid dashboard (T2 #3) → ADR-027.
- Scenario range and anchoring — DECIDED: Q33B = E, Q33C = rounded ₹100 grid + current level + 0-P&L, Q33D = C → ADR-008.

## Q204 — OPEN — Shared data feed vs each user's own Zerodha feed
- **Where it stands.** The owner decided (T2 #121) that the interim source is Zerodha live data through **each user's
  own Zerodha API connection**. That is a per-user feed. ADR-012 (Q98, Q170, T2 #102) wants one shared feed fanned
  out to all users, which only a licensed vendor can give. So in V1 the shared-feed goal cannot be met for live
  prices; shared *calculations* can still run once per market, but only on data each user is allowed to see.
- **Recommended:** accept per-user feeds for V1 and keep the gateway ready for a shared licensed feed; record that the
  5k→500k scale saving waits for the vendor licence. **Cost:** one Zerodha WebSocket per active user (Zerodha limits
  per API key are unverified here).
- Spec basis: ADR-012, ADR-014; T2 #102, #121, #122.

## Q205 — OPEN — Monitoring while the user's Zerodha session has expired
- Zerodha sessions end every morning (owner, T1 #265). Under per-user Zerodha data, a user who hasn't logged in today
  has no data feeding their active strategy, so no exit alert can fire.
- Example: an Iron Condor is active, the user doesn't log in Monday, NIFTY falls 400 points at 11:00 → no Red alert.
- **Recommended:** show *"Monitoring paused — reconnect Zerodha"* (Q182 already requires this), send a morning
  reconnect reminder, and state plainly in onboarding that monitoring needs a live daily session until a vendor feed
  exists. Q89 (monitoring continues after Pro expiry) cannot be met without a session either.
- Spec basis: ADR-010, ADR-015 (Q182, Q184), ADR-020, ADR-023 (Q89).

## Q206 — DECIDED (spec-conformant, 2026-09-29; no new rule: follows Q185/Q186, Q92, ADR-034) — Prices for drafts and trials without Zerodha
- Drafts without Zerodha are allowed and must not show fake prices (Q185, Q186). Q9 originally meant users could
  explore the chain without a broker; the interim Zerodha source removes that.
- **Recommended:** keep drafts price-less ("Connect Zerodha to see live prices") and allow a clearly labelled
  **Sample · Not Live** chain (as Q92 already allows) for learning.
- Spec basis: ADR-020 (Q185–Q188), ADR-023 (Q92).

## Q207 — DECIDED → ADR-041 (owner, 2026-09-29: A) — Futures leg payoff formula
- Futures Buy/Sell are V1 legs (Q8); the locked formulas cover options only.
- **Recommended:** BUY FUT `(Market − Entry) × Qty`, SELL FUT `(Entry − Market) × Qty` (expiry), with LTP for live.
- Spec basis: ADR-008, `spec/business-rules/scenario-calculations.md` §1.

## Q208 — DECIDED → ADR-042 (owner, 2026-09-29: A) — Scenario and range step for SENSEX
- All 100-point steps (Q33, Q108) were discussed on NIFTY; SENSEX trades roughly 3× higher (not re-measured today).
- **Measured 2026-09-29** from Zerodha's public instrument list (api.kite.trade/instruments): NIFTY (NFO) strike gap
  **50** points (128 of 137 gaps), lot size **65**; SENSEX (BFO) strike gap **100** points (151 of 151), lot size **20**;
  nearest expiries 2026-09-29 (NIFTY) and 2026-10-01 (SENSEX). Worked examples in the spec that use quantity 75 are
  illustrative only; the real lot size always comes from the instrument master (ADR-007 Q36).
- **Recommended:** step per underlying as configuration; pick SENSEX's after checking its real strike spacing.
- Spec basis: ADR-005 (Q108), ADR-008 (Q33C).

## Q209 — DECIDED → ADR-044 (owner, 2026-09-29: A) — How a referral's success reaches the platform
- A referral counts only when an account is opened and attributed (Q61); no mechanism is recorded.
- **Recommended:** admin imports confirmed openings (CSV, like ADR-024), each creating an entitlement event.
- Spec basis: ADR-024, ADR-025.

## Q210 — DECIDED → ADR-034 (email Zerodha first; owner, 2026-09-29) + EXTERNAL (waiting on Zerodha's written answer) — What Zerodha allows, and what it costs each user
- ChatGPT's check of Zerodha's docs on 28 Sep (T2 #122): the free Personal plan has no live
  data; live data needs the ₹500/month Connect plan per API key; Kite Connect data may not be displayed or
  redistributed on other platforms; startups building mass-retail products may get Kite Connect free.
- **Verified by us, 2026-09-28, on Zerodha's own pages:**
  - support.zerodha.com "What are the charges for Kite APIs": Personal (free) "excludes historical or real-time data";
    Connect gives "real-time data via WebSockets" and "historical candle data", "₹500 per app each month";
    Startups: "For startups developing mass retail products, Kite Connect APIs are free", contact Zerodha's API team.
  - support.zerodha.com "Can I use historical and live data … on other platforms?": "you cannot display data from
    Kite Connect APIs on other platforms, as this violates the exchange's data vending policies … Kite Connect API
    is primarily an execution suite, not a data vending service"; for distribution, "contact an exchange-authorised
    data vendor".
  - kite.trade/startups: "If your platform is targeted at the mass retail market, the Kite Connect APIs are available
    free of cost"; the page does **not** say whether the free startup access includes live market data or permits
    display on our platform.
  - Consequence (open for owner decision): the T2 #121 premise "Zerodha's live market data, which is free" is not
    true for the Personal plan, and showing Kite Connect data in our product is refused by default. Unmeasured:
    whether the startup programme changes either point — only Zerodha's written answer settles it.
- The owner's plan (T2 #121) assumed the live data was free. If each user must create their own Connect app, each
  user pays Zerodha ₹500/month on top of ₹600 for Pro — a very different product.
- **Recommended:** email Zerodha's API team first (startup/mass-retail programme + written permission for our SaaS
  display); verify the Zerodha facts from their pages; build nothing that depends on the answer until it arrives.
- Spec basis: ADR-014 (Q177 provisional), ADR-020 (Q178 setup guide).

## Q211 — DECIDED (owner, 2026-09-29: not a blocker for building) — Compliance review before these features go live
Strategy discovery and suggested setups; adjustment approaches; notification content; a paid subscription sold by a
registered Zerodha Authorised Person; market-data display and derived data; Zerodha API terms; retention of the
anti-abuse record after deletion (Q96, India's DPDP Act). The chats already flagged SEBI/exchange review as a product
requirement (T1 #26). Nothing here is a conclusion; these features stay out of production until reviewed.
- **Owner decision (2026-09-29):** asked whether Q211 blocks REQ-025/027/045/046/068/069, the owner answered "They
  are not blocked. Proceed." Building these requirements goes ahead (they are marked Approved). Whether a compliance
  review is still wanted before they reach production will be put to the owner in the release brief for the first
  release that contains them (every production release needs the owner's approval anyway).

## Q212 — DECIDED / DONE (2026-09-29) — Data used in the owner's YouTube adjustment video
The owner shared an Iron Condor adjustment video (T2 #93) so that the data layer covers every value it uses; ChatGPT
could not read the transcript and the owner will provide it later (T2 #95). Pending: the transcript, then a line-by-
line data checklist (REQ "Adjustment data requirements from the owner's reference video").
- **2026-09-29:** the owner said Q211/Q212 are "not blocked. Proceed." The link was already in the chat (T2 #93:
  youtu.be/BpIyvYL5ahE); the transcript was extracted (30m46s, youtube-transcript-api) and the 30 values it uses are
  listed in spec/technical-design/adjustment-data-contract.md. REQ-071 is Approved. Open: the meaning of 7 unclear
  values (rows 10, 12, 13, 24, 25, 26, 28) — asked separately.

## Q213 — DECIDED (delegated overnight, ADR-045: recommendation A = both) — Breakeven columns: inserted, at the end, or both?
Q33D inserts 0-P&L columns at their price position; the earlier locked column list (T1 #90) also has Lower BE /
Upper BE after the grid. **Recommended:** both (inserted markers for reading the grid, summary columns for the
numbers). Spec basis: ADR-008.

## Q214 — DECIDED (delegated overnight, ADR-045: about 5 seconds, admin-configurable) — How long Undo stays after removing a leg
Q56 chose "remove + Undo"; the follow-up question (duration) was paused and never answered. **Recommended:** about 5
seconds (ChatGPT's recommendation, T1 #170). Spec basis: ADR-007.

## Vendor enquiries — EXTERNAL
TrueData (owner emailed; phone call said an "NSE certificate" is needed), Global Datafeeds (email drafted to
sales@globaldatafeeds.in), NSE Data & Analytics (marketdata@nse.co.in, not yet contacted), BSE (not yet contacted).
Record each reply in ADR-014 when it arrives.

## Open areas with no question yet (become Q-numbers when work needs them)
Pricing model for "Estimated Now" · bid/ask/slippage · charges model · tick rounding · timeout/cancel/repricing ·
MIS/NRML · expiry/multi-expiry execution edge cases · quantity edge cases · existing-position grouping algorithm ·
alert provider, consent, quiet hours, templates, escalation, dedupe, rate limits · adjustment rule priority/conflict/
cooldown · security architecture · data-retention policy · admin/system-health screens · final cloud/stack · the
strategy state transition table (proposal in `spec/data/domain-model.md`) · what happens when a Client ID leaves the
complimentary list · Zerodha rate limits for per-user WebSockets.

## Q215 — DECIDED → ADR-035 — Expiry P&L: entry price or current price? (audit item X-T1#95)
- Owner, 2026-09-29: **A** — expiry columns use the entry price; the LTP only in the live P&L column (Q33A = C).
- Spec basis: ADR-008; `spec/business-rules/scenario-calculations.md` §1–§2; T1 #95–#97.

## Q216 — DECIDED → ADR-036 — Beta first, or public launch? (audit item Q13)
- Owner, 2026-09-29: **A** — public SaaS as chosen at Q13 = B; invite-only switch exists, off by default.
- Spec basis: ADR-001 (Q13 = B, T1 #27), REQ-003.

## Q217 — DECIDED → ADR-037 — Can a Limited user exit an active strategy? (audit item C-5)
- Owner, 2026-09-29: **A** — yes; exit and closing orders for active strategies are allowed; new trades stay Pro.
- Spec basis: ADR-023 (Q67/Q89/Q91), REQ-018, ADR-018.

## Q218 — DECIDED → ADR-038 — Referral reward: calendar month or 30 days? (audit item C-3)
- Owner, 2026-09-29: **A** — 30 days per referral, day count in Admin, exact end date shown.
- Spec basis: ADR-025 (Q63), REQ-021, ADR-026 (T1 #189).

## Q219 — DECIDED → ADR-039 — A running trial meets an already-trialled Client ID (audit item C-4)
- Owner, 2026-09-29: **A** — the running trial ends; offer the verified transfer or Pro.
- Spec basis: ADR-023 (Q88), ADR-022 (Q82/Q83), REQ-014.

## Q220 — DECIDED → ADR-040 — Which system sends the WhatsApp OTP? (audit item C-19)
- Owner, 2026-09-29: **A** — shared Notifier gateway, Wati AUTHENTICATION template, stand-in sender in dev/test.
- Spec basis: ADR-021 (Q72), REQ-012 AC-2/AC-4.

## Q221 — DECIDED → ADR-043 — Tech stack
- Owner, 2026-09-29: **A** — Python 3.12+ / FastAPI, PostgreSQL, Redis, Vue 3 + Vite; legacy code may be copied with
  provenance (`spec/technical-design/legacy-reuse.md`).
- Spec basis: none before this (the spec had no stack decision); hard rules ADR-008, ADR-012, ADR-029.

## Q223 — DECIDED (owner, 2026-09-29 morning: keep A) — Close Partial Strategy while the platform's own entry order is still open (W-023 orchestrator default OD-m)
- Situation: some legs filled, one entry order (e.g. BUY 23,600 CE) is still open at Zerodha, and the user picks Close
  Partial Strategy. If that entry order fills after the exits, it leaves a new position; for a condor's short call the
  mirror case is a naked short.
- Orchestrator default in W-023 (flagged, not settled): the Close preparation also LISTS a cancel request for each of the
  platform's own still-open entry orders on that strategy, shown to the user before confirmation. Nothing is sent
  without the user's confirmation; W-023 builds the list only (`backend/ofo/execution/partial.py`, OD-m).
- Recommendation: keep it (A). Alternative (B): do not offer Close until the open entry order is terminal.
- **Owner decision (2026-09-29): A.** The Close preparation lists a cancel request for each of the strategy's own
  still-open entry orders, shown with the exits and confirmed by the user together; nothing is sent without that confirm.
- Spec basis: ADR-017 Q27 (Close Partial Strategy is a user choice; executed legs never unwound automatically), ADR-018
  Q198 (a mismatch is reconciled through a prepared order), REQ-058 AC-3, REQ-059 (exits require no unresolved mismatch).
  None of these says what happens to an open entry order when the user closes.

## Q222 — DECIDED (delegated overnight, ADR-045; CONFIRMED by the owner 2026-09-29) — Does a fresh agreeing reconciliation run unblock a strategy by itself?
- Situation: a mismatch blocked a strategy (ADR-018); a later run finds the broker agreeing again.
- Decision (recommendation A, applied overnight): NO automatic unblock. The block lifts only through a recorded manual
  resolution on the latest run (adopt, prepared closing order, broker flat → exited), so the user sees what happened in
  the account before trading resumes. Cost: one extra action after an external change.
- Alternative B: an agreeing run clears the block automatically (and records it).
- Spec basis: ADR-018 "allows recorded manual reconciliation, and blocks ... while a mismatch is unresolved"; REQ-060
  AC-5 "Manual reconciliation is allowed". Neither requires nor forbids an automatic clear; the independent verifier of
  W-021 judged A the safer default.
- Built in W-021 (`backend/ofo/reconciliation/`).

## Q224 — DECIDED (delegated overnight, ADR-045; CONFIRMED by the owner 2026-09-29) — A contract held by more than one strategy disagrees with Zerodha
- Situation: strategies A and B each SELL 23400 CE x50; Zerodha nets them per contract. If the user squares off in Kite
  (broker 0) or partly (broker −50), nothing tells the platform which strategy's leg changed.
- Finding (W-021 verifier, 2026-09-29): splitting by "broker minus the other holders' platform quantity" invented a
  +50 long for A on a flat account; adopt wrote it into A, and the prepared closing order proposed SELL 100 (would OPEN
  a −100 short).
- Decision (recommendation, applied overnight — SPEC CHANGE to the ADR-018 Q198 resolution list for this case only):
  for a contract held by two or more non-exited strategies whose broker quantity disagrees, the per-strategy
  resolutions that need an attribution (adopt broker position, prepared closing order, broker flat → exited) are
  REFUSED and every holder stays blocked; "mark as requiring attention" and "review and modify" stay available. The
  user resolves by trading in Kite (or by later modifying a strategy) and running reconciliation again. Single-holder
  contracts (with or without a recorded standalone) are unchanged.
- Open for the owner: an attribution rule for shared contracts (e.g. the user picks which strategy absorbs the change,
  recorded and audited), which would restore adopt/close/exit for this case.
- Spec basis: ADR-016/ADR-018 (Zerodha is the authority; a mismatch blocks); ADR-018 Q198 resolution list; REQ-060
  AC-5, AC-7 (AC-7 covers one strategy plus a standalone, not two strategies). No spec text defines attribution across
  strategies.

## Q225 — DECIDED (owner, 2026-09-29 morning) — Entitlement history after a setting changes; post-dated status changes
- Situation (W-007 round 4, issue #12): a revoke dated 2106 was accepted and then blocked a real revoke; lowering
  `max_free_days` 90 → 30 made a legal stored history fail to load.
- Decision: A — validate new events against current settings; load stored history with integrity checks only; every
  status change bounded to effective_at ≤ recorded_at + clock skew. Recorded in ADR-023 "Owner decision (Q225)".

## Q226 — DECIDED (owner, 2026-09-29 morning) — Strictness of the advice-word check (W-024, issue #30)
- Decision: strict — ban bare "best", "sure", "safe", "guarantee*", "recommend*" in platform templates, with the named
  exceptions "best bid", "best ask", "best-case", "make sure"; broker/user text quoted only. Recorded in ADR-003
  "Owner decision (Q226)".

## Q227 — DECIDED (owner, 2026-09-29 morning) — Guided scenario column headings (W-004, issue #21)
- Decision: each scenario column is headed by its level (CURRENT and 0-P&L marked); "NIFTY at expiry | You make/lose"
  is the scenario section's caption. Recorded in REQ-035 "Owner clarification (Q227)".

## Q228 — DECIDED (owner, 2026-09-29 morning) — Length of a paid month / year
- Decision: 30 days / 365 days, fixed; not calendar months. Recorded in ADR-023 "Q228". (Was owner-review item 3b.)

## Q229 — DECIDED (owner, 2026-09-29 morning) — Entitlement evaluation rules 2-3
- Decision: both confirmed as written in ADR-023 "Evaluation rules". Recorded in ADR-023 "Q229".

## Q230 — DECIDED (owner, 2026-09-29) — Q226 edge cases (W-024 round 5)
- Decision: ban all word forms of the five words; do not ban "must"/"have to"/"ought to"; exceptions match exactly as
  spelled. Recorded in ADR-003 "Q230".

## Q231 — DECIDED (owner, 2026-09-29) — Is "safety" banned by the Q230 word-form rule?
- Decision: no — "safety" (and "safety check/checks/gate") is a reviewed exception. Recorded in ADR-003 "Q231".

## Q232 — DECIDED (owner, 2026-09-29) — Which UX level shows Greeks (REQ-006 AC-3 vs REQ-035 AC-7)
- Decision: Advanced only (REQ-035 wins); REQ-006 AC-3 corrected. No code change (W-004 already follows REQ-035).

## Q233 — DECIDED (owner, 2026-09-29) — Strategy table TOTAL row: P&L % and Entry Value
- Decision: TOTAL P&L % = unrealized P&L ÷ max loss ("—" if unlimited); Entry Value only for options-only strategies.
  Recorded in REQ-035 "Owner decision (Q233)".

## Q234 — DECIDED (owner, 2026-09-29) — Zerodha Client ID format
- Decision: 6 characters, 2–3 letters then digits (AB1234 or ABC123). Recorded in REQ-020 "Owner decision (Q234)".

## Q235 — DECIDED (owner, 2026-09-29) — Trust boundary for the advice-wording check (W-024 round 6)
- Decision: same boundary as W-026 (accidental misuse by own code, CI-flagged internals; runtime sabotage out of scope);
  promise phrases added to the checker. Recorded in ADR-003 "Q235".

## Q236 — DECIDED (owner, 2026-09-29) — TOTAL Entry Value: net or plain sum?
- Decision: NET entry premium (sells − buys) × quantity, Cr/Dr labelled; golden condor ₹6,825 Cr. Corrects the
  orchestrator's ambiguous "signed as the legs" in REQ-035 "Owner decision (Q233)".

## Q237 — DECIDED (owner, 2026-09-29) — CI for the API/web layers on a private repo
- Decision: (a) a path-filtered project workflow `app-tests.yml`; usage reported after a week. Recorded in ADR-046.

## Q238 — DECIDED (owner, 2026-09-29) — Order of exit orders (OD-e)
- Decision: shorts bought back first, then longs sold, never in one batch. Recorded in REQ-058 "Owner decision (Q238)".

## Q239 — DECIDED (owner, 2026-09-29) — Gate checks on exits (W-014)
- Decision: keep all five checks on exits. Recorded in REQ-059 "Owner decision (Q239)".

## Q240 — DECIDED (owner, 2026-09-29) — REQ-039 strategy state transition table
- Decision: the proposed table in spec/data/domain-model.md §6 is approved with two fixes: Reconciliation Required is
  left only by a recorded manual resolution (Q222); Active ↔ Monitoring Paused only on the user's pause/resume.
  REQ-039 is now Approved.

## Q241 — DECIDED (owner, 2026-09-29) — Moneyness column in the strategy table
- Decision: no — leave it out; the locked column order stays. Recorded in REQ-035.

## Q242 — DECIDED (owner, 2026-09-29) — Scenario caption at every level; TOTAL P&L % "—" cases
- Decision: caption at all three UX levels; TOTAL P&L % "—" also for a missing live price or a multi-expiry strategy.
  Recorded in REQ-035.

## Q243 — DECIDED (owner, 2026-09-29) — Five gaps in the approved state table (found building W-041)
- Decision: apply all five fixes, written into spec/data/domain-model.md §6: (1) nothing filled → back to Validated
  with reasons; (2) Review Manually is not a transition; (3) an adjustment proposal can be withdrawn (recorded) → Active;
  (4) partial fills → Partially Executed, Reconciliation Required only on a real broker mismatch; (5) "any live state"
  = Active, Monitoring Paused, Adjustment Proposed, Execution in Progress, Partially Executed.

## Q244 — DECIDED (owner, 2026-09-29) — Catalogue truncation guard
- Decision: contract-level — refuse any update that removes a not-yet-expired contract; the 50% per-index rule goes.
  Recorded in REQ-053 "Owner decision (Q244)".

## Q245 — DECIDED (owner, 2026-09-29) — Adjustment with every order rejected, nothing filled
- Decision: back to Adjustment Proposed with the rejection reasons; the original version stays active; the user may
  execute the proposal again or withdraw it. Recorded in spec/data/domain-model.md §6.

## Q246 — DECIDED (owner, 2026-09-29) — Readings of unclear values in the reference video (REQ-071)
- Decision: profit left = max profit − booked losses; capital = margin blocked; volatility = per-option IV; swing /
  trend out of V1. Recorded in spec/technical-design/adjustment-data-contract.md "Owner readings".

## Q247 — DECIDED (owner, 2026-09-29) — Where a strategy goes after adopting Zerodha's position
- Decision: adopt → Active on the adopted version (from any prior state); closing order executed or broker flat →
  Exited. Found by the W-041 verifier (Partially Executed → RR → adopt got stuck). Recorded in domain-model §6.

## Q248 — DECIDED (owner, 2026-09-29) — Pricing model and rate for delta / IV values (REQ-071 rows 4, 26)
- Decision: use the existing §4 Black-Scholes model; risk-free rate is an admin setting, default 6.5% p.a., recorded
  with each calculation. Rows 4 and 26 → pass. Recorded in adjustment-data-contract.md.

## Q249 — DECIDED (owner, 2026-09-29) — Strike selection modes (REQ-027 AC-1)
- Decision: short-strike delta bands — Conservative 0.10–0.15, Balanced 0.20–0.25, Aggressive 0.30–0.35; wings at
  template defaults; all strikes editable. Recorded in REQ-027.

## Q250 — DECIDED (owner, 2026-09-29) — Valid setup and effective range (REQ-069, REQ-068 AC-4)
- Decision: valid = listed + within capital/max-loss + P&L ≥ 0 over the whole range (range-bound) or at the favourable
  end (directional); effective range = the breakeven band. Recorded in REQ-069.

## Q251 — DECIDED (owner, 2026-09-29) — Strategy levels, market views, objectives (REQ-068 AC-2)
- Decision: apply the level rules directly (Beginner / Intermediate / Advanced as listed in REQ-068), plus market view
  and objective per strategy. Recorded in REQ-068 "Owner decision (Q251)".

## Q252 — DECIDED (owner, 2026-09-29) — Default playbooks vs the "no user rule" case (REQ-045 AC-5/AC-7)
- Decision: adopt-to-own — unadopted defaults are platform detections; adopted/edited defaults are the user's rules;
  edits create personal copies. Recorded in REQ-045.

## Q253 — DECIDED (owner, 2026-09-29) — Platform "risk area" detection (REQ-045 AC-2)
- Decision: 0.5% from a short strike/breakeven, or 50% of max loss, or ≤2 DTE with a short leg within 1%; all
  admin-configurable. Recorded in REQ-045.

## Q254 — DECIDED (owner, 2026-09-29) — Expected move; "material" change
- Decision: expected move = spot × ATM IV × √(days/365) (REQ-027); material = structure change or ≥5% move in max loss
  or a breakeven (REQ-068). The question's example said ±332; the correct value is ±383 (recorded).

## Q255 — DECIDED (owner, 2026-09-29) — Building an approach's exact configuration (REQ-046 AC-4)
- Decision: keep widths, restore the short strikes' entry distance from spot (snapped to listed strikes); always an
  editable proposal. Recorded in REQ-046.

## Q256 — DECIDED (owner, 2026-10-02) — The clock-skew window value (ADR-023 Q225)
- Question: ADR-023 names a clock-skew window for new entitlement events but gave no number.
- Decision: **60 seconds, both ways**, the value the verified strategy-version and timeline modules already use. An
  event the ledger stamps at 10:00:00 may carry a granted/effective date from 09:59:00 to 10:01:00; anything outside
  is refused. Recorded in ADR-023 "Q256".

## Q257 — DECIDED (owner delegation, 2026-10-02) — An existing contract arrives with revised terms (REQ-053)
- Question: Zerodha's daily list carries a stored contract (same token) with a different lot size (exchanges revise
  lot sizes on live contracts). The W-053 build first refused the whole update, which would freeze the catalogue.
- Decision (orchestrator as product owner, under the owner's 2026-10-02 instruction to decide by role; basis REQ-053
  AC-1 and ADR-016, Zerodha is final): lot size, tick size, expiry and trading symbol follow the source list and every
  change goes to an append-only history; identity fields never change and a list changing them is refused with
  nothing written. Recorded in REQ-053 "Q257". Found by the W-053 adversarial review (PR #109).
- Amended 2026-10-02 (owner, ADR-050): the identity list now names (exchange segment, exchange token), not Zerodha's
  instrument_token (spec/findings.md F-01, F-02); see REQ-053.

## Q258 — OPEN (external: Zerodha + legal) — Does the platform count as an "algo provider" under SEBI's 2025 framework?
- Question: SEBI's retail algo framework (circular SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013, 4 Feb 2025; NSE
  INVG67858) requires orders from a whitelisted static IP (Zerodha rejects others from 1 Apr 2026, and limits static IP
  sharing to family), an algo ID on API orders, and exchange empanelment for algo providers with every strategy
  registered. Our SaaS sends many unrelated users' orders from our server through each user's own Kite session, each
  order confirmed by the user. Does that make us an algo provider needing empanelment, and how is the static-IP rule met
  for many users? (spec/findings.md F-06 - secondary sources, unverified.)
- Recommendation: ask Zerodha in the pending written-answer thread (ADR-034) and include it in the Q211 legal review.
  The broker phase (build plan P4) stays blocked until it is answered. Bears on REQ-054, REQ-063, REQ-066.
- **Primary text read 2026-10-07 (F-11, F-12):** SEBI makes brokers the principal and any algo provider "providing the
  facility to place algo orders with Brokers through API" an agent that must be empanelled with exchanges (F-11, para
  I(a), III(a)). NSE: "A static IP can only be mapped to one client at a time", family excepted; for an empanelled
  provider's algos the IP "shall be that of the vendor or the client" (F-12, A.5, A.7). Still open: whether
  user-confirmed orders prepared by our rules are "algo orders" (definitions/FAQs, stream S1a) and Zerodha's own rules.
