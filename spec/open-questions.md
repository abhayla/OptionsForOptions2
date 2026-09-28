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

## Q206 — OPEN — Prices for drafts and trials without Zerodha
- Drafts without Zerodha are allowed and must not show fake prices (Q185, Q186). Q9 originally meant users could
  explore the chain without a broker; the interim Zerodha source removes that.
- **Recommended:** keep drafts price-less ("Connect Zerodha to see live prices") and allow a clearly labelled
  **Sample · Not Live** chain (as Q92 already allows) for learning.
- Spec basis: ADR-020 (Q185–Q188), ADR-023 (Q92).

## Q207 — OPEN — Futures leg payoff formula
- Futures Buy/Sell are V1 legs (Q8); the locked formulas cover options only.
- **Recommended:** BUY FUT `(Market − Entry) × Qty`, SELL FUT `(Entry − Market) × Qty` (expiry), with LTP for live.
- Spec basis: ADR-008, `spec/business-rules/scenario-calculations.md` §1.

## Q208 — OPEN — Scenario and range step for SENSEX
- All 100-point steps (Q33, Q108) were discussed on NIFTY; SENSEX trades roughly 3× higher (not re-measured today).
- **Recommended:** step per underlying as configuration; pick SENSEX's after checking its real strike spacing.
- Spec basis: ADR-005 (Q108), ADR-008 (Q33C).

## Q209 — OPEN — How a referral's success reaches the platform
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

## Q211 — LEGAL — Compliance review before these features go live
Strategy discovery and suggested setups; adjustment approaches; notification content; a paid subscription sold by a
registered Zerodha Authorised Person; market-data display and derived data; Zerodha API terms; retention of the
anti-abuse record after deletion (Q96, India's DPDP Act). The chats already flagged SEBI/exchange review as a product
requirement (T1 #26). Nothing here is a conclusion; these features stay out of production until reviewed.

## Q212 — EXTERNAL — Data used in the owner's YouTube adjustment video
The owner shared an Iron Condor adjustment video (T2 #93) so that the data layer covers every value it uses; ChatGPT
could not read the transcript and the owner will provide it later (T2 #95). Pending: the transcript, then a line-by-
line data checklist (REQ "Adjustment data requirements from the owner's reference video").

## Q213 — OPEN (small) — Breakeven columns: inserted, at the end, or both?
Q33D inserts 0-P&L columns at their price position; the earlier locked column list (T1 #90) also has Lower BE /
Upper BE after the grid. **Recommended:** both (inserted markers for reading the grid, summary columns for the
numbers). Spec basis: ADR-008.

## Q214 — OPEN (small) — How long Undo stays after removing a leg
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
