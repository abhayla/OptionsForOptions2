# Master register of research findings (2026-10-21)

## Purpose

One list of every item raised by today's research. Each item appears once and has one status against the spec. It
answers three questions: is it already built, is it already decided, and who decides the rest. Claude writes the
requirements for WRITE rows later. OWNER rows go to the owner one question at a time (queue at the end).

This file is a register, not a decision. It changes no ADR and no REQ.

## Sources (all dated 2026-10-21)

| Id | Source | Cited as |
|---|---|---|
| A | Sensibull study gap list (`docs/research/sensibull-study-2026-10-21/gap-list.md`, rows B1-B55, E1-E10, W1-W6, D1-D5, P1-P9, O1-O2, C1-C7, A1-A7, X1-X9, G1-G12, and the six "must be different" points DF1-DF6) plus the superseded draft plan (plan-only items cited "PL"; kept privately, outside this public repo, with the study's README, because they name a competitor's internal endpoints) | "A B7", "A DF2", "PL S2" |
| B | Multi-broker architecture review of 10 apps (private) | "MB L3" (Part A layer), "MB B1.3" (Part B app 1, extra 3, in table order), "MB T4" (trap) |
| C1 | OFO2 architecture gaps (private) | "GAPS G2", "GAPS AH1" (row 1 of the "already ahead" table), "GAPS LH1" (loophole 1) |
| C2 | Chat review of the owner's proposed architecture: where Claude disagreed | "C2 D1" |
| C3 | Chat list of items missing from the owner's proposal | "C3 M5" |
| C4 | Owner's proposed architecture (`owner-proposed-architecture.md`) | "C4 §3.5" (section 3, bullet 5), "C4 §5-p" (the paragraph under section 5), "C4 P6" (core principle 6) |

The spec was checked on branch `docs/master-register-2026-10-21` (from `main` at `e528e2cf`): `views/spec-digest.md`,
then greps of `spec/decisions` and `spec/requirements` by each item's key terms. Code was checked only to fill the
Built column, by Glob/Grep on `backend/ofo`, `backend/ofo_app` and `frontend/src`. "unverified" means the file was not
opened.

## Classification key

| Class | Meaning |
|---|---|
| BUILT | Decided and implemented. Cites the ADR/REQ and a code path. |
| DECIDED | An ADR or REQ covers it, not built. Says when a REQ lacks an acceptance criterion (AC) for it. |
| WRITE | Claude may write a requirement. Allowed only when all three tests pass: (1) no ADR clash; (2) no money shown or charged, pricing, legal/SEBI, paid spend, data licence or prod deploy; (3) a studied app shows it working. |
| OWNER | Goes to the owner: SPEC CHANGE (ADR quoted), Business, Compliance, or Unsure. A recommendation is given where possible. |
| REJECT | Not for this product. One-line reason. The owner can veto any reject. |
| TECH | Internal technical design with no user-visible scope. Claude decides later, with a reviewer. |
| DEFERRED | The owner said to decide it later and ignore it for now; no new decision is recorded (MR-140). |

A class followed by "(held)" means the requirement is written as Draft and not live for users until the named check clears (Q211 legal review, data or display licence, consent, static IP); when it is built is the owner's call (ADR-150 (3)).

## Owner decisions so far (2026-10-21)

- (a) All three research sources go into one register, and this morning's Sensibull plan is folded in.
- (b) The register and the Draft REQs live in the repo, as one docs PR at the end. The freeze is lifted for that PR only.
- (c) The three-test rule decides what Claude may write. The owner can veto any row.

---

### Owner answers during triage
- Q-1 (2026-10-21 ~17:05 IST), rows MR-004, MR-008, MR-029, decision ADR-150: split. MR-008 (Shift / Width / Hedge) is
  WRITE now; MR-004 and MR-029 are written as Draft requirements HELD until Q211 clears. MR-043 follows MR-004 (held).
- Q-2 (~17:15 IST), row MR-020, decision ADR-151: "Go with what Sensibull does" = target level, target date and IV
  change, all from the server engine. SPEC CHANGE to ADR-120 (1). MR-020 is WRITE (REQ-034 AC-6 to be rewritten).
- Q-3 (~17:20 IST), decision ADR-152: Sensibull is the standing default for user-facing features; the owner is
  still asked on (a) OFO2-stricter safety, (b) compliance/legal, (c) money/business. Re-triage under it: MR-012
  (typed entry price), MR-014 (summary money figures), MR-017 (existing positions in margin) and MR-124 (paper
  tracking) become WRITE. MR-015 (POP) becomes WRITE for the number, and its label goes to the owner under (b). REJECT
  rows that Sensibull has are re-checked against (a)-(c) before the PR.
- Q-4 (~17:25 IST), row MR-112, decision ADR-153: the Sensibull way. A stop-loss / conditional exit is held at
  Zerodha as a trigger the platform creates after one user confirmation. SPEC CHANGE to ADR-009 for exits only.
  Core proof first: whether the trigger endpoint needs the static IP (ADR-100, row MR-148). MR-112 is WRITE.
- Q-5 (~17:30 IST), row MR-148, decision ADR-154: plan B as intent. First prove whether the trigger endpoint needs a
  static IP; if it does, prefer one platform-owned IP registered through Zerodha; per-user rental only as the
  fallback; no spend without the owner. MR-148 is DECIDED (intent).
- Q-6 (~17:35 IST), row MR-140 hosting: owner said "this will be decided later. Ignore for the time being". ADR-054
  stands ("decided when Stage 4b starts"); no new decision. MR-140 is DEFERRED.
- Q-7 (~17:40 IST), row MR-059, decision ADR-155: "same as Sensibull". Prices delayed by 1 minute, a "connect
  Zerodha" banner and paper planning before a broker login. SPEC CHANGE to ADR-027. It cannot go live in production
  until data permission is in writing. MR-059 is WRITE (with a launch dependency).
- Q-8 (~17:45 IST), rows MR-015, MR-150, MR-067, MR-151, MR-157, MR-155, decision ADR-156: all six follow Sensibull
  and are WRITE, each HELD until its named check clears (legal wording, DPDP consent, data licence, redistribution,
  tool cost, content cost).
- Q-9 (~17:50 IST), rows MR-133, MR-134, MR-135: "Keep as decided, held". ADR-023, ADR-024 and ADR-026 stand, held
  by ADR-055 (2). MR-133 and MR-134 are DECIDED (held). MR-135 is REJECT ("not now"). No new decision.
- Q-10 (~17:55 IST), row MR-137, mentor/family read-only access: "Not in V1, later idea". MR-137 is REJECT for V1,
  recorded as a later idea. No new decision.
- Re-triage under ADR-152 (~18:00 IST): MR-021 (IV per strike / IV change) becomes WRITE under ADR-151. MR-045,
  MR-127 and MR-152 stay REJECT (compliance, exception b). MR-083 stays REJECT (the owner's architecture says
  "Zerodha-only"). MR-071, MR-081, MR-093 and MR-094 stay REJECT (not Sensibull user features). Seven clashes go to
  the owner: MR-003, MR-026/066/068, MR-090, MR-092, MR-031, MR-138, MR-069.
- Q-11 (~18:00 IST), row MR-003, decision ADR-157: NIFTY, BANKNIFTY, FINNIFTY and SENSEX; no stock options, screener or
  heatmaps. SPEC CHANGE to ADR-001. MR-003 is WRITE (indices only).
- Q-12 (~18:05 IST), rows MR-026, MR-066, MR-068, decision ADR-158: history, IV and OI charts as Sensibull has them,
  held until display rights are confirmed in writing. SPEC CHANGE to ADR-066 and REQ-047 AC-1. All three rows are
  WRITE (held).
- Q-13 (~18:10 IST), row MR-090, decision ADR-159: MIS offered as in Sensibull, against the recommendation. The
  auto square-off is stated before Execute and reconciliation recognises it. SPEC CHANGE to ADR-080 (1). MR-090 is
  WRITE.
- Q-14 (~18:15 IST), row MR-092, decision ADR-160: an Orders page, a funds view and an order import as in Sensibull;
  Zerodha stays the authority, with read times shown. Cancel/modify stay on Zerodha because ADR-100 blocks API orders.
  SPEC CHANGE to ADR-134. MR-092 is WRITE.
- Q-15 (~18:20 IST), rows MR-031, MR-069, MR-138, decision ADR-161: all three as in Sensibull. Manual P&L sits on
  its own labelled line. FII/DII is held for a data source. Native apps are in scope, with timing left to
  prioritisation. SPEC CHANGE to ADR-001 and ADR-102. All three rows are WRITE.
- Q-16 (~18:40 IST), row MR-112 follow-up, decision ADR-162: price-level stops are held at Zerodha. P&L stops are
  executed automatically by the platform server after one user confirmation (against the recommendation). Launch
  dependencies: the static IP (ADR-154), Zerodha's written confirmation of algo standing (F-17, Q258/Q259) and Q211.
  Until then it runs on replay and paper only.
- Q-17 (~18:45 IST), ADR-150 (3): "held" means not live; WHEN to build is the owner's call at prioritisation.
- Q-18 (~18:50 IST), ADR-163: Execute always sends the whole strategy; no "Trade N" of ticked legs (exception a).
- Q-19 (~18:55 IST), ADR-164: max profit and max loss as % of funds, as in Sensibull. SPEC CHANGE to ADR-055 (1) for
  that figure, against the recommendation.
- Owner queue complete at ~18:20 IST. Next: TECH rows decided by Claude with a reviewer, then Draft REQs for every
  WRITE row, then one docs PR.
- MR-130 (phase order) moved to the prioritisation pass, which the owner said comes later.
- Correction: the kill switch (ADR-127/128) and the market-hours check (ADR-119) are in held PRs #463 and #455, not
  on main. The 2026-10-21 chat list C3 M5/M6 was wrong to call them built.

## 1. Customer screens and builder

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-001 | Strategy Builder reachable from the menu | A B1, C4 §1.3 | ADR-007, REQ-034, F-49 | Yes: `frontend/src/router/routes.js:11` | BUILT | F-49 fixed |
| MR-002 | NIFTY and SENSEX underlyings | A B2 | ADR-001, REQ-001 | Yes: `LegPicker.vue` | BUILT | |
| MR-003 | Other underlyings (BANKNIFTY, FINNIFTY), stock options, stock screener and heatmaps | A B3, A A4 | ADR-001, REQ-001 | No | WRITE | ADR-001: "underlyings NIFTY (NSE) and SENSEX (BSE)". A later scope question, not a V1 gap |
| MR-004 | Ready-made shapes that load into the builder at strikes placed by a fixed rule from ATM; Learn "Open in Builder" | A B4, A X5, PL S2 item 1, PL D2, MB L7 | ADR-055 (1), ADR-006, REQ-027, REQ-028 | Partial: 21 templates in `backend/ofo/strategy/catalogue.yaml`, shown only on Learn | WRITE (held) | SPEC CHANGE to ADR-055 (1): "no platform-picked strikes, stop-losses, targets or adjustment instructions presented as the platform's view". Rec: yes, labelled "Strikes placed by a fixed rule - change them", after the legal check (Q211/Q261). Asked together with MR-008 and MR-029 |
| MR-005 | Shape name on the leg list ("Iron Condor", "Custom Strategy") and hedge legs marked | A B5, MB B1.5, GAPS G6c, C3 M15 | ADR-006 (Q52: unmatched = "Custom Strategy"), REQ-028 | Partial: `backend/ofo/strategy/matching.py`, not on the screen | DECIDED | REQ-028 has no AC for showing the name in the builder; add one |
| MR-006 | A different expiry per leg (calendars, diagonals) | A B6, MB L7 | ADR-006, ADR-083, ADR-143 | Partial: per-leg expiry in `LegPicker.vue`; no worst-case loss for mixed expiries (ADR-143) | DECIDED | |
| MR-007 | Strike -/+ stepper on each leg, over the real strike list | A B7 | none (searched: stepper, strike step; REQ-030 has only a lot stepper) | No | WRITE | (1) no clash; (2) no money; (3) Sensibull study §1 |
| MR-008 | Shift / Width / Hedge: move, widen or re-hedge every strike in one click, computed on the server | A B8, MB L7, MB B1.6, GAPS G6b, C3 M15, PL S2 item 3, PL proof2 | ADR-055 (1), ADR-008 | No | WRITE | SPEC CHANGE to ADR-055 (1) (same quote as MR-004): the platform picks the new strikes. Rec: may proceed, because it only moves strikes the user chose (plan S2) |
| MR-009 | Lots per leg | A B9, MB L7 | REQ-030 | Yes: `LegPicker.vue:34` | BUILT | |
| MR-010 | Multiplier that scales every leg | A B10 | none (searched: multiplier, scale) | No | WRITE | (1) no clash; (2) no new money figure; (3) Sensibull study §1 |
| MR-011 | Tick box to leave a leg out of the numbers ("what if I drop the hedge?"), analysis only | A B11, A DF1 | ADR-002, ADR-017 | No | WRITE | (1) no clash if Execute is refused while any leg is left out; (2) no new money figure; (3) Sensibull study §1 |
| MR-012 | Type my own entry price per leg, with Reset Prices | A B12 | ADR-068 (1), ADR-075 | Partial: captured planned entry only | WRITE | Unsure: ADR-068 (1) "A draft leg's entry price is its planned entry"; a typed price changes what P&L is measured from. Rec: allow, labelled "your price", reset returns to the captured price |
| MR-013 | Market depth popup per leg in the builder | A B13 | ADR-080 (depth used for pricing) | Partial: 5-level depth used on Execute (W-097) | WRITE | (1) no clash; (2) prices only, no money figure; (3) Sensibull study §1 |
| MR-014 | New money figures on the builder summary: net premium Pay/Get, itemised charges, time and intrinsic value totals, reward/risk ratio | A B14, A B15, A B19, A B21 | ADR-008, ADR-071, ADR-082 | Partial: net premium on Execute (W-102), charges total inside max profit/loss (W-075) | WRITE | Business (new money shown). Rec: yes, every figure from the engine, none in the browser |
| MR-015 | Probability of profit (POP) | A B20, PL D4 | ADR-008 (Q15 uses "Estimated probability of profit: ~73%" as its precision example), REQ-032, ADR-055 (1) | No | WRITE (held) | Compliance: ADR-055 (1) bars an "expected return ... as a performance claim". Rec: yes, labelled "a model probability from today's prices, not a forecast" |
| MR-016 | Funds, margin needed, margin available, and a shortfall warning in the builder | A B22, A B23, A DF3 | ADR-016, ADR-099 | Yes: `frontend/src/components/strategy/MarginLine.vue` | BUILT | Ahead of Sensibull, which showed no warning |
| MR-017 | Count existing positions in the margin figure | A B24 | ADR-094, REQ-055, F-39 | No | WRITE | Business (changes the margin figure shown). Rec: yes, later, using Zerodha's own position-aware figure |
| MR-018 | Payoff chart at expiry, max profit / max loss tiles, breakevens | A B16, A B17, A B25, C4 §1.4, C4 §4.4, C4 §4.8 | ADR-008, ADR-089, REQ-034 | Yes: `PayoffChart.vue`, `SummaryCards.vue` | BUILT | |
| MR-019 | "Now" curve drawn over the expiry curve, hover shows both | A B26, A B27 | REQ-034 AC-6, ADR-120 | Partial: the API returns one view per call (`backend/ofo_app/routes/outcome.py:151`) | WRITE | (1) draws only the two ADR-120 modes, no third mode; (2) no new money kind; (3) Sensibull study §1. Add a chart AC to REQ-034 |
| MR-020 | What-if at a target index level and a target date; breakeven at that date | A B18, A B36, A B37, GAPS G6d, PL S1, PL D3 | ADR-120 (1), REQ-034 AC-6 | No | WRITE | SPEC CHANGE to ADR-120 (1): "No what-if sliders (spot, implied volatility or days to expiry) in the Strategy Builder in V1". Rec: yes for level and date, no for IV |
| MR-021 | Edit IV per strike, IV offset | A B38 | ADR-120 (1) | No | WRITE | ADR-120 excludes IV what-if; the plan also recommends keeping it out |
| MR-022 | Open-interest bars on the payoff chart | A B28 | none for the chart (searched: OI, open interest); uses live OI only | No | WRITE | (1) live OI, no history, so no ADR-066 clash; (2) no money; (3) Sensibull study §1 |
| MR-023 | Expected-move (one and two SD) bands on the chart | A B29 | REQ-027 (Q254 formula), REQ-034 AC-4 | No | DECIDED | Formula decided; REQ-034 lacks an AC for drawing it |
| MR-024 | Per-leg scenario table, range and step, P&L columns, Greeks, TOTAL row | A B30, A B31, A B32, A B33, C4 §1.5, C4 §1.6, C4 §4.5, C4 §4.6, C4 §4.7 | ADR-008, ADR-042, REQ-033, REQ-035 | Yes: `backend/ofo/table/`, `StrategyTable.vue` (unverified) | BUILT | |
| MR-025 | Greeks totals with rupee examples on hover | A B34 | REQ-035 (Greeks at Advanced) | Partial: TOTAL row sums Greeks (`backend/ofo/table/model.py`) | WRITE | (1) no clash; (2) explains a figure, no new one; (3) Sensibull study §1 |
| MR-026 | Price history chart of the strategy | A B35, PL S4 | ADR-066 | No | WRITE (held) | ADR-066: "shows users no historical market data"; plan S4 recommends no |
| MR-027 | Show the futures (forward) price per expiry | A B39 | ADR-061 | Internal only | WRITE | (1) no clash; (2) a price, not money; (3) Sensibull study §1. Low value |
| MR-028 | Leg picker that shows LTP, OI and Greeks per strike, with tabs | A B42 (prices part) | ADR-012 | Partial: one leg at a time, no prices (`LegPicker.vue:2`) | WRITE | (1) prices come from the platform (ADR-012); (2) no money; (3) Sensibull study §1 |
| MR-029 | Straddle / strangle quick picks 50-200 points from ATM | A B42 (quick-pick part), PL S2 item 2 | ADR-055 (1) | No | WRITE (held) | SPEC CHANGE to ADR-055 (1) (same quote as MR-004). Rec: yes after the legal check |
| MR-030 | Pick legs in the option chain (Buy/Sell, lots) and import them | A B43 | REQ-030, ADR-131, ADR-132 | Held: PR #466 (W-120) | DECIDED | |
| MR-031 | Manual P&L for past adjustments | A B44 | ADR-102 | No | WRITE | ADR-102 builds P&L from real broker fills; value low |
| MR-032 | Save a strategy (draft) and reload it exactly | A B45, A D1, C4 §1.7, C4 §2.4 | ADR-062, ADR-075, REQ-038 AC-5 | Yes: `SaveDraftBar.vue`, `backend/ofo_app/strategy_store.py` | BUILT | A name field is unverified |
| MR-033 | "My Strategies" page with search | A B46 | REQ-009 AC-2, REQ-038 AC-5 | Held: PR #393 (W-109) | DECIDED | |
| MR-034 | Share a read-only link to a plan | A B47, PL 1c | REQ-035 (W-073 draft link), ADR-027, ADR-055 (3) | Partial: draft opens from a URL (`frontend/src/lib/draftLink.js`) | WRITE | (1) no clash if the viewer must log in (ADR-027) and nothing is ranked (ADR-055 (3)); (2) no money; (3) Sensibull study §1 |
| MR-035 | Builder history and undo on screen | A B48, PL 1c | REQ-070 | API only: `backend/ofo_app/routes/strategies.py:360` | DECIDED | |
| MR-036 | Analyse my live positions in the builder | A B49 | REQ-061, ADR-084, ADR-096 | Blocked: W-083 | DECIDED | |
| MR-037 | Builder warnings as codes: weekend or holiday decay, unhedged short, low liquidity, event, expiry day | A B50 | ADR-003 (Q226), ADR-011 (Q159), W-086 | Partial: expiry-day warning only | WRITE | (1) no clash; text from the reviewed catalogue (ADR-003); (2) no money; (3) Sensibull study §2. Warn only on a measured condition |
| MR-038 | Underlying locked while legs exist (never silently cleared) | A B51, A DF4 | ADR-019 | Yes: `LegPicker.vue:42` | BUILT | |
| MR-039 | Live price push at most once a second | A B52 | ADR-012, REQ-049 | Yes: W-065, `backend/ofo_app/live_push.py` | BUILT | |
| MR-040 | Guided / Standard / Advanced levels | A B53 | ADR-004, REQ-006 | Yes: `StrategyBuilderPage.vue:43` | BUILT | |
| MR-041 | Plain-language outcome sentences | A B54 | ADR-071, REQ-034 AC-7 | Yes: `SummaryCards.vue` | BUILT | |
| MR-042 | Guided create: "where will NIFTY go?" to a few explained setups | A W1 | ADR-005, ADR-121, ADR-122, ADR-124, REQ-024, REQ-069 | Held: PR #457 (W-119) | DECIDED | F-51 needs a correction (see MR-145) |
| MR-043 | Risk-labelled variants of one view (Conservative / Balanced / Aggressive) | A W2, PL S2 item 4 | REQ-027 AC-1 (four modes), ADR-055 (1) | No | WRITE (held) | Modes decided in REQ-027; built only after the legal check that ADR-055 waits on |
| MR-044 | "How this trade works" bullets next to a loaded strategy | A W3 | REQ-011, ADR-003 | Partial: Learn page only | WRITE | (1) no clash; (2) no money; (3) Sensibull study §3 |
| MR-045 | Wizard that ranks trades by profit; "YOLO" expiry ladder | A W4, A W5, A DF5 | ADR-003, ADR-055 (3) | No | REJECT | ADR-055 (3): "no 'best', 'winning' or ranking wording" |
| MR-046 | Home dashboard and market overview | A X1, C4 §1.1 | ADR-027, REQ-008 | Yes: `HomeOverviewPage.vue`, `MarketContextPage.vue` | BUILT | |
| MR-047 | Live option chain | A C1, C4 §1.2, C4 §3.4 | REQ-029 | Yes: `OptionChainPage.vue`, `backend/ofo_app/chain_push.py` | BUILT | Change column shows "-" (F-47) |
| MR-048 | Chain Advanced columns: IV, Greeks, bid/ask; also intrinsic, time value, breakeven % | A C2, A C5 | REQ-029 (Advanced: IV, Greeks, bid/ask, liquidity) | No | DECIDED | Intrinsic, time value and breakeven % have no AC; add them |
| MR-049 | Chain OI bars and OI change % | A C3 | REQ-029 | Partial: OI on the socket, no bars | DECIDED | |
| MR-050 | Chain per-lot toggle, ITM shading, number of strikes around ATM | A C4 | REQ-029 (no AC for these) | No | WRITE | (1) no clash; (2) no money; (3) Sensibull study §7 |
| MR-051 | Chain live preview while legs are selected | A C6 | REQ-031 | No | DECIDED | |
| MR-052 | "Prices have changed since you saved" marker and an explicit re-price action | PL 1c | ADR-075, ADR-085 | No | WRITE | (1) never re-prices silently, so no clash; (2) no new money kind; (3) Sensibull study §1 |
| MR-053 | Turn a saved draft into real trades | A D3 | ADR-062, REQ-056 | Yes: `StrategyActions.vue:4` | BUILT | |
| MR-054 | Learn pages per strategy | A X5 (pages part) | REQ-011 | Yes: `LearnPage.vue` | BUILT | "Open in Builder" is in MR-004 |
| MR-055 | Broker connection and account information screen | C4 §1.10 | ADR-020, REQ-015 | Yes: `BrokerSettingsPage.vue` | BUILT | |

## 2. Market data

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-056 | Live prices from each user's own Kite feed, normalised on the server and pushed over websockets; the browser never touches the broker | A G10, MB L5, MB B9.1, C4 §3.2, C4 §3.6, C4 §8.4 | ADR-012, ADR-053, REQ-048, REQ-049 | Yes (owner account): `backend/ofo/marketdata/`, `backend/ofo_app/kite_ws.py` | BUILT | |
| MR-057 | Data health: timestamps, freshness, stale data never used as live, monitoring paused | MB L10 (feed-stale), MB B3.2, C4 §3.5, C4 §3.7, C4 §6.2 | ADR-015, ADR-065, ADR-077, REQ-049, REQ-072 | Yes: `backend/ofo/marketdata/feed_health.py` | BUILT | |
| MR-058 | Licensed market-data feed as the long-term source; each user's own Kite data until then | MB L5, MB B4.5, C2 D4, C4 §3.1, C4 P3 | ADR-014, ADR-053, REQ-052 | No | DECIDED | Buying the licence is a later owner spend call |
| MR-059 | Prices before a broker login (delayed data, paper trading on live data), public pages with data, free tools as a funnel | A B55, A G8, MB L5, MB B1.7, MB B7.6, MB B9.1, MB B10.1, GAPS G5 | ADR-027, ADR-053, ADR-014, ADR-034, F-23 | No | WRITE (held) | Business (data licence): ADR-027 "All live data is behind login". Rec: ask Zerodha/a vendor what may be shown; keep ADR-027 until a written answer |
| MR-060 | Instrument master once a day; one contract identity (segment, exchange token, expiry); token reuse handled | MB L4, MB T7, GAPS AH5, C3 M8, C4 §3.3 | ADR-050, ADR-052, ADR-057, ADR-058, ADR-059, ADR-104, REQ-053 | Yes: `backend/ofo/instruments/` | BUILT | |
| MR-061 | Live data and broker order updates in their own process with an internal bus, not inside the API process | MB L1, MB L5, MB B8.6, GAPS G2, C2 D6, C4 P1 | ADR-012, ADR-043, ADR-053, REQ-050 | No: in-process `backend/ofo/marketdata/fanout.py` | TECH | Needed before multi-user (200 users = 200 sockets in the API process) |
| MR-062 | Redis only once there are two or more processes | C2 D5, C4 §8.2 | ADR-043, ADR-012 | No | TECH | |
| MR-063 | Binary websocket packets | MB B1.10 | none | No | TECH | Verdict Partly; JSON is fine at our size |
| MR-064 | Freeze limits: weekly manual refresh; automatic NSE fetch parked | C3 M7, GAPS LH3 | ADR-091, ADR-092 | Yes (manual) | TECH | A data-refresh mechanic; #488 waits on an approval for a new external source |
| MR-065 | Market context strip: ATM IV, PCR, max pain, India VIX | A B40 (part) | ADR-012, ADR-053 | No: `MarketContextPage.vue:2` lists none | WRITE | (1) derived from the user's own feed (ADR-053); (2) no money, no new licence; (3) Sensibull study §1 |
| MR-066 | IV percentile, IV chart, OI over time, straddle charts | A B40 (IV percentile part), A A1, A A3, A A5 | ADR-066 | No | WRITE (held) | ADR-066: "shows users no historical market data" in V1 |
| MR-067 | Events calendar and "events that can affect this trade" | A W6, A A6, A B40 (events part) | none (searched: event, calendar) | No | WRITE (held) | Business: needs an outside data source. Rec: later |
| MR-068 | TradingView chart with OI profile | A B41 | ADR-066, ADR-012 | No | WRITE (held) | Licence plus ADR-066; low value |
| MR-069 | FII / DII data | A A2 | none | No | WRITE | Outside data source; low value for an index-options planner |

## 3. Calculation engine

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-070 | One server-side engine for every number on every screen; expiry, live and model views kept separate | A G9, MB L6, GAPS AH6, C4 §4.1, C4 §4.2, C4 §4-p, C4 P4 | ADR-008, REQ-032, REQ-034 AC-6, AC-8 | Yes: `backend/ofo/engine/`, `backend/ofo_app/routes/outcome.py` | BUILT | |
| MR-071 | Second pricing engine in the browser for instant sliders | MB B3.1 | ADR-008 | No | REJECT | ADR-008: one engine owns every number |
| MR-072 | Pricing model (Black-Scholes-Merton with q from the parity forward; same price as Black-76) | MB L6, GAPS AH10 | ADR-061, ADR-063 | Yes: `backend/ofo/engine/` | BUILT | Not a gap |
| MR-073 | Futures legs | C4 §4.3 | ADR-041 | Yes (REQ-033 Verified) | BUILT | |
| MR-074 | Expiry maths on one fixed IST clock | MB L6, MB T10, GAPS AH7, C3 M10 | scenario-calculations §4 | Yes: `backend/ofo/timeutil.py` | BUILT | |
| MR-075 | Exact decimal money, one quantity unit, one instrument id | MB T3, GAPS AH6, C3 M10 | ADR-008, project decimal-money rule | Yes: `backend/ofo/money.py` | BUILT | |
| MR-076 | Margin asked from Zerodha, never computed; any estimate only a labelled preview | MB L6, C2 D1, C4 §4.9, C4 §5.2 | ADR-016, ADR-094, ADR-099, REQ-055 | Yes: `backend/ofo_app/kite_margin.py`, `outcome_margin.py` | BUILT | C4 "margin estimates" is answered by ADR-094 |
| MR-077 | Fast Greeks with a matching fallback | MB B3.5 | ADR-008 | n/a | TECH | Verdict Partly; speed not needed now |
| MR-078 | Core proof: builder edit loop on live data (latency, max loss to the paisa) and the Shift/Width/Hedge server proof | PL core, PL proof2 | ADR-008, ADR-030 | Not run | TECH | Step 1 of any builder work |

## 4. Broker and execution

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-079 | Broker adapter layer with one answer shape; OpenAlgo layout as a reference only | MB L3, MB B2.1 | ADR-029, ADR-050, REQ-054, F-08, F-13 | Yes: `backend/ofo/broker/` | BUILT | AGPL: ideas only, never code (F-13) |
| MR-080 | Named capability flags per broker | MB L3, MB B1.1, GAPS G7 | ADR-017 ("A broker-specific capability matrix when more brokers come"), ADR-029 | No | TECH | Cheap now in the adapter interface |
| MR-081 | Broker id in every API path | MB B1.2 | ADR-001 | n/a | REJECT | Verdict Partly; the broker stays in the server session |
| MR-082 | Broker session: encrypted token, daily expiry, reconnect prompt | A G1, MB L2, MB L12, C3 M4, C4 §5.1, C4 §8.5 | ADR-020, ADR-053, REQ-015, REQ-063 AC-5 | Yes (owner only): `backend/ofo_app/broker_crypto.py`, `broker_token_store.py` | BUILT | |
| MR-083 | More brokers, several accounts per user, one order across accounts, broker gateways | A G3, MB L2, MB B4.3, MB B5.5, MB B6.2, MB B7.4, MB B9.3 | ADR-001, REQ-002 | No | REJECT | ADR-001 "Zerodha as the only broker"; REQ-002 own account only |
| MR-084 | Orders go as a read-only Kite basket the user places; no per-leg send; the user is present for every trade | A E1, A E2, A DF2, MB L8, MB B5.2, MB B6.1, C4 §5.3 | ADR-054, ADR-081, REQ-073, ADR-002 | Yes: `ExecuteStrategyPage.vue`, `backend/ofo_app/basket_post.py` | BUILT | |
| MR-085 | Hedge legs before the sells that need them (two baskets) | A E3, MB T1, MB B1.4, GAPS AH1, C4 §5-p | ADR-017, ADR-117, REQ-056 | Yes: `backend/ofo/execution/sequence.py` | BUILT | |
| MR-086 | Unique tag per order; plan stored before the basket returns; survives a restart | MB L8, MB T4, MB B5.1, GAPS AH2, C3 M2, C4 P7 | ADR-105, REQ-073 | Yes per GAPS AH2 (tag file unverified) | BUILT | |
| MR-087 | Partial execution is an explicit exception the user resolves; no automatic retry; a timeout is not a failure | MB L8, MB T2, MB B4.1, MB B5.4, MB B7.1, GAPS AH8, C4 §5-p, C4 §6.5, C4 §6.6 | ADR-017, ADR-079, ADR-116, ADR-123, ADR-136, ADR-137, REQ-058 | Yes: `backend/ofo/execution/partial.py` | BUILT | GAPS did not compare the UX with AlgoTest's Halt screen |
| MR-088 | No freeze slicing: a leg above the freeze limit is blocked | A E7, MB L8, GAPS AH8, C3 M7 | ADR-081, ADR-092 | Yes: `backend/ofo/execution/freeze.py`; PR #420 held | BUILT | |
| MR-089 | Market protection: depth-based limit price with slippage | A E6 | ADR-080, ADR-095 | Yes: W-078 | BUILT | |
| MR-090 | Intraday (MIS) product | A E8 | ADR-080 | No | WRITE | ADR-080: every order is NRML, no product choice |
| MR-091 | Order status after placing (four states) and an Orders screen, one line per strategy order | A E10, A O2, C4 §1.8, C4 §5.3 | ADR-135, ADR-138, REQ-057 | Partial: return check `ReturnCheck.vue`; Orders page not on main (PRs #451/#452) | DECIDED | |
| MR-092 | Broker's full order book, funds drawer, import of the order book | A O1, A P8, A D5 | ADR-134 | No | WRITE | ADR-134: the app links to the broker, never rebuilds it |
| MR-093 | Smart order (send a target position size) | MB B2.2 | ADR-002, ADR-019 | No | REJECT | Verdict Not useful; every order belongs to a strategy |
| MR-094 | Automated strategies, signal webhooks in, AI/script hosting, retail developer API, scalping tools, backtest-style monitoring | MB L7, MB L10, MB B2.6, MB B3.4, MB B7.3, MB B9.2, MB B10.2 | ADR-009, ADR-017, F-17, F-18 | No | REJECT | Auto-trading or algo-provider duties; ADR-009 "assisted, not autonomous" |
| MR-095 | Order and route rate limits; broker-busy back-pressure | MB L8, MB L12, MB B2.7, C4 §2.5 | REQ-063 | Unverified: "429"/"semaphore" in `kite_client.py` not read | TECH | |
| MR-096 | Signed server-to-server requests; idempotent webhook receivers | MB L12, MB B5.3, MB B6.4 | none | No | TECH | Only if an API or inbound webhook is exposed |
| MR-097 | Positions and order state read from the broker with a short cache; order-update stream | MB L9, C4 §5.4 | ADR-134, REQ-060 | Yes: `backend/ofo_app/broker_sync.py`, `kite_reads.py` (order-update stream unverified) | BUILT | |
| MR-098 | Execute loses a prepared plan on reload; next Prepare refused with a misleading message | GAPS LH1 | ADR-105, REQ-065 | Defect open | TECH | Fix as a defect class |

## 5. Risk controls

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-099 | Margin shortfall blocks the basket | A E4, A DF3, MB T8, GAPS AH3, C4 §6.3 | ADR-016, ADR-094, REQ-055 | Yes: `backend/ofo/execution/margin_gate.py` | BUILT | |
| MR-100 | A reconciliation mismatch blocks new orders until Zerodha agrees | MB L9, GAPS AH4, C3 M1, C4 §5.5 | ADR-018, ADR-116, ADR-137, REQ-060 | Yes: `backend/ofo/reconciliation/blocking.py` | BUILT | Not seen in any studied app |
| MR-101 | Check every leg before anything is sent: permitted contracts, quantities, eligibility | MB L8, C4 §2.5, C4 §4.10, C4 §6.1 | ADR-104, REQ-053, REQ-059, REQ-063 AC-4 | Yes (REQ-059 Verified) | BUILT | |
| MR-102 | Risk tiers on the Execute review | A E5 | ADR-140, ADR-143, REQ-056 | Unverified | DECIDED | |
| MR-103 | Market hours and holiday calendar on execution | A E9, C3 M6, C4 §6.4 | ADR-119 | Held: PR #455 (grep `market_hours` in `backend`: 0 hits) | DECIDED | C3 said "built"; it is not on main |
| MR-104 | Kill switch | A E9, MB L10, C3 M5, C4 §6.4 | ADR-127, ADR-128 | Held: PR #463 (grep `kill_switch` in `backend`: 0 hits) | DECIDED | C3 said "built"; it is not on main |
| MR-105 | Every safety gate fails closed | MB T6, MB B2.3 | ADR-018, ADR-094, REQ-059 | Yes: `margin_gate.py`, `blocking.py` | BUILT | |
| MR-106 | Nothing reaches the broker without the user's explicit approval | MB B2.3, C2 D3, C4 §6-p | ADR-009, ADR-011, ADR-054, REQ-042 | Yes by design (basket route) | BUILT | |
| MR-107 | Audit trail of important actions and executions | MB L12, C4 §2.6, C4 §6.7 | ADR-029, REQ-040, REQ-064 | Yes: `backend/ofo_app/audit_store.py`, `order_audit.py` | BUILT | |
| MR-108 | Egress gate: the API process reaches only the database and Kite | GAPS AH9 | REQ-063 | Yes: `backend/ofo/broker/egress.py` | BUILT | |

## 6. Positions, adjustments and monitoring

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-109 | Positions screen: strategy-linked positions and outside lots | A P1, C4 §1.8, C4 §5.4 | REQ-044, ADR-110, ADR-134 | Branch only: W-111 | DECIDED | |
| MR-110 | The strategy is the position group; adopt outside positions | A P2 | ADR-002, ADR-084, REQ-061 | Yes by design; adoption blocked (W-083) | BUILT | |
| MR-111 | Exit a strategy | A P3 | REQ-056, ADR-117 | Yes: `ExecuteStrategyPage.vue:5` | BUILT | |
| MR-112 | Where stop-loss and conditional exits live: our alert plus a prepared basket, or Zerodha's own GTT/ATO triggers | A P4, A P5, MB L10, GAPS G3 | ADR-009, ADR-053, ADR-100, ADR-134, REQ-042 | No | WRITE | Business (what a beginner's stop-loss is promised to do when our server or the daily token is down). Rec: our alert + prepared basket first (decided), then offer a user-confirmed Zerodha trigger link (ADR-134) |
| MR-113 | Rule engine: user rules for entry, exit and adjustment, evaluated on live data | A P5, MB L10, C4 §4.10, C4 §7.3, C4 §7-p | ADR-011, ADR-064, ADR-069, REQ-041 | Domain only: `backend/ofo/rules/`; nothing runs it | DECIDED | |
| MR-114 | Background workers for monitoring, reconciliation, data finalising and alerts, with restart recovery; never for order placement | MB L9, MB B3.3, GAPS G3, C2 D3, C4 §7.1, C4 §8.3, C4 P7 | ADR-009, ADR-112, REQ-043 | No: the lifespan starts only the live market | TECH | |
| MR-115 | Four health colours per active strategy | A P6, C4 §7.1 | ADR-010, REQ-043 | No: badge only (`LiveStrategyCard.vue`) | DECIDED | |
| MR-116 | Alert plus a prepared exit basket when a rule fires | A P5, A X7 | REQ-042 | No | DECIDED | |
| MR-117 | Notifications through the shared Notifier (in-app, push, email, WhatsApp); no generic outbound webhooks | A X7, MB L10, MB B8.3, GAPS G3, C3 M11 | ADR-028, ADR-040, REQ-062 | No: `AlertsPage.vue` shell | DECIDED | |
| MR-118 | Event bus so alert channels never sit in the order path | MB B2.5 | none | No | TECH | |
| MR-119 | Strategy P&L: realised and open, from broker fills | A P7, C4 §7.2 | ADR-102, ADR-103 | Domain: W-091 in review; no screen | DECIDED | |
| MR-120 | Adjustment opportunities: from user rules, or a generic risk-area warning, with Before/After | C2 D2, C4 §1.9, C4 §7.4 | ADR-011, ADR-055 (1), REQ-045, REQ-046, REQ-071 | Domain: `backend/ofo/adjustment/`; no screen | DECIDED | Platform-picked adjustments stay barred by ADR-055 (1) |
| MR-121 | Record whether each suggestion was accepted, rejected or completed | C4 §7.5 | REQ-040, REQ-037 (searched accepted/rejected/dismiss in REQ-040..046: 0 hits) | No | DECIDED | Triggers and confirmed changes are recorded; no AC links a suggestion to its outcome. Add one |
| MR-122 | Orders placed outside the platform are detected | MB L9, MB B6.3, C3 M9 | ADR-018, REQ-060 | Partial: reconciliation | DECIDED | |
| MR-123 | Daily "does Zerodha agree with us" report to the user | MB L9, MB B8.1, GAPS G8 | REQ-060 (continuous only) | No | WRITE | (1) no clash; (2) reports matches, no new money figure; (3) Tradetron (MB B8) |
| MR-124 | Paper tracking of a saved plan (P&L since saved, paper exit), per strategy, never a global switch | A D2, MB L8, MB B2.4, MB B8.2, MB B10.1, MB T5 | ADR-002, ADR-062; spec silent (searched: paper trad, virtual, simulated trad) | Partial: Live Strategies follows saved plans | WRITE | Business (new virtual money figures). Rec: yes |
| MR-125 | Notes on a strategy | A D4 | none (searched: notes, journal) | No | WRITE | (1) no clash; (2) no money; (3) Sensibull study §4 |
| MR-126 | Immutable strategy versions for approved executions | C4 P5 | REQ-038 AC-2, AC-3, ADR-019, ADR-105 | Unverified | DECIDED | |
| MR-127 | Verified P&L sharing, leaderboards, copy-trading marketplace, "Verified Live" badge, live P&L carousel | A P9, A X2, MB B8.4, MB B8.5 | ADR-003, ADR-055 (1), (3) | No | REJECT | ADR-055 (3): no marketplace, no ranking |

## 7. Accounts, auth and plans

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-128 | Multi-user sign-in (Google + WhatsApp OTP) with a broker session per user | A G1, A G2, MB L2, GAPS G1, C4 §2.1, C4 P8 | ADR-021, ADR-022, ADR-040, REQ-003, REQ-012, REQ-014 | No: one fixed owner user (`backend/ofo_app/routes/broker.py:78`) | DECIDED | GAPS rates it CRITICAL; timing is MR-130 |
| MR-129 | Every read and write scoped to the signed-in user on the server | C4 §2.2, C4 P6 | REQ-002, REQ-003 (no per-user scoping AC; searched: isolat, multi-tenant) | No | WRITE | (1) no clash; (2) none; (3) every multi-tenant app (MB L1) |
| MR-130 | Phase order (builder, then safety, then monitoring, then guided) and where multi-user sign-in fits | PL D5, GAPS G1 | ADR-030, ADR-112, REQ-067 | n/a | OWNER | Business (product sequencing). Rec: approve the order, but build MR-128/MR-129 before any per-user feature |
| MR-131 | Entitlement engine | C4 §2.3, C4 §6.4, GAPS G10 | ADR-023, REQ-017 | Yes: `backend/ofo/entitlements/`, `entitlement_store.py` | BUILT | |
| MR-132 | 7-day trial and Limited mode | A G4 | ADR-023, ADR-037, REQ-018 | Engine done (W-007); policy blocked (W-008) | DECIDED | |
| MR-133 | Paid plan, payments, and which side is paid (planning or monitoring) | A G5, PL S3, PL D1, MB L11, MB B4.6, MB B6.5, GAPS G10, C4 §1.11 | ADR-026, ADR-055 (2), ADR-144, ADR-146, REQ-023, F-26 | Billing shell only (`BillingShellPage.vue`) | DECIDED (held) | Business, deferred: ADR-055 (2) holds until Q260/Q211 |
| MR-134 | Free Pro for Zerodha users; builder free on one broker | A G6, MB B1.9 | ADR-024, ADR-055 (2), REQ-019 | Paused (W-011) | DECIDED (held) | Business, deferred with MR-133 |
| MR-135 | Other revenue lines: white-label, licensable charting, broker-branded sites | MB B1.8, MB B8.7, MB B10.3 | ADR-055 (2) | No | REJECT | Business. Rec: not now |
| MR-136 | Account settings, email change, account deletion, DPDP duties | C3 M13, C4 §1.11 | REQ-013, REQ-074, ADR-022, F-27 | No | DECIDED | C3 said "not decided"; REQ-013 and REQ-074 cover it |
| MR-137 | Read-only access for a mentor or family member | MB B4.2 | REQ-002 | No | REJECT | Business/Compliance. Rec: not in V1 |
| MR-138 | Native mobile app | A G7 | ADR-001 | No | WRITE | ADR-001: "responsive web from day 1 with no native apps" |

## 8. Data, infrastructure and operations

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-139 | PostgreSQL is the durable source of truth; logical modules kept separate | C4 §8.1, C4 §8-p, C4 P2 | ADR-043, ADR-062, ADR-105 | Yes: `backend/ofo/` domain, `backend/ofo_app/` app, Alembic | BUILT | |
| MR-140 | Hosting, deploy pipeline, hosted staging separate from production | A G12, MB L1, GAPS G9, C3 M12 | ADR-054 (hosting decided when Stage 4b starts), REQ-067 | No hosted staging | DEFERRED | Business (spend and prod deploy). Rec: decide before MR-061 and MR-114 are built |
| MR-141 | Error tracking, uptime alerts, backups with restore drills | A G11, GAPS G9, C3 M12 | REQ-067, REQ-074 | No | TECH | Free-tier tools; any paid tool goes to the owner |
| MR-142 | Drop late replies so an old answer never draws over a newer edit | MB B1.3, GAPS G6a | none (searched: request id, stale reply) | No | TECH | |
| MR-143 | Land the held, reviewed PR stack in the plan's order | PL held list, GAPS LH4 | ADR-106 | n/a | TECH | |
| MR-144 | A just-reconnected screen hits DATA_UNHEALTHY before the first tick | GAPS LH2 | ADR-015, REQ-049 | Defect open | TECH | |
| MR-145 | Register the study's findings (F-51 correction, no shortfall warning in Sensibull, partial sends, lots vs units, mechanical ATM rule) | PL F1, PL F2, PL F3, PL F4, PL F5 | F-51, spec-first R6 | Not registered | TECH | Spec bookkeeping in the docs PR |
| MR-146 | Never design from a vendor's docs alone | MB T9 | none | n/a | TECH | Process rule |
| MR-147 | Support tool: look up one user's order trail | C3 M14 | REQ-064, REQ-020, REQ-063 AC-5 | Partial: `backend/ofo/admin/`, `audit_store.py` | WRITE | (1) no clash; (2) admin only, allowlisted fields (REQ-063 AC-5); (3) audit logs in OpenAlgo (MB L12) |

## 9. Compliance and legal

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-148 | SEBI retail-algo rules avoided through the basket route; a written plan B if Zerodha calls the basket "algo" | MB L12, MB B4.4, MB B7.2, GAPS G4, C3 M3, C4 P9 | ADR-054, ADR-100, F-06, F-11, F-12, Q258, Q259 | n/a | DECIDED | Business (cost per user of a static IP or VM). Rec: write plan B as intent now, no build |
| MR-149 | Live trading and licences are explicit launch dependencies | C4 P9 | REQ-066, ADR-055, Q211 | Specified | DECIDED | |
| MR-150 | Product analytics and session replay | A G11 | REQ-063, REQ-074 | No | WRITE (held) | Compliance (user data to a third party, DPDP consent). Rec: privacy-safe page counts only |
| MR-151 | Download the option chain as Excel | A C7 | REQ-052, F-23 | No | WRITE (held) | Compliance (redistributing exchange data). Rec: no for V1 |
| MR-152 | Market verdicts, trade ideas, research-analyst algos | A A7, A DF6, MB B7.5 | ADR-003, ADR-055 (1), F-24 | No | REJECT | Advice; needs SEBI Research Analyst registration |

## 10. Product UX extras

| ID | Item (plain words) | Sources | Spec today | Built? | Class | Reason / owner question |
|---|---|---|---|---|---|---|
| MR-153 | Mindful pre-trade check-in (today's count, a short pause, "Have you checked your exit plan?") | A X3 | none (searched: mindful, check-in, cooling-off) | No | WRITE | (1) no clash; (2) no money; (3) Sensibull study §9 |
| MR-154 | Instrument watchlist | A X4 | none (legacy map skipped it: "no REQ") | Partial: Live Strategies | WRITE | (1) no clash; (2) no money; (3) Sensibull study §9. Low value |
| MR-155 | Video courses | A X6 | REQ-011 | No | WRITE (held) | Business (content scope and cost). Rec: later |
| MR-156 | Dark theme | A X8 | none (searched: dark) | No | WRITE | (1) no clash; (2) no money; (3) Sensibull study §9 |
| MR-157 | Support chat, FAQ, "What's New" | A X9 | REQ-010 (FAQ on the public site) | No | WRITE (held) | Business (support channel and its cost). FAQ itself is decided |

---

## Reconciliation

Every source item id below is cited by at least one row. A source item cited by several rows was split on purpose.

| Source | Items read | Rows citing it | Notes |
|---|---|---|---|
| A gap list | 122 rows (B 55, E 10, W 6, D 5, P 9, O 2, C 7, A 7, X 9, G 12) + 6 "must be different" points = 128 | 101 | All 128 ids found |
| A plan only (PL) | 18 (S1-S4, D1-D5, price-drift marker cited as "PL 1c", core proof, second proof, held list, findings F1-F5) | 15 | All 18 found |
| B (MB) | 79 (L1-L12, Part B 57 extras, T1-T10) | 60 | All 79 found |
| C1 (GAPS) | 27 (AH1-AH10, G1-G5, G6a-G6d, G7-G10, LH1-LH4) | 34 | All 27 found |
| C2 | 6 (D1-D6) | 7 | All 6 found |
| C3 | 15 (M1-M15) | 20 | All 15 found |
| C4 | 70 (§1 11, §2 6, §3 7, §4 10 + §4-p, §5 5 + §5-p, §6 7 + §6-p, §7 5 + §7-p, §8 5 + §8-p, P1-P9) | 48 | All 70 found |
| Total | 343 source items | 157 rows | Rows by class after triage (the Class column below): BUILT 45, DECIDED 33, WRITE 49, OWNER 1, REJECT 10, TECH 18, DEFERRED 1 |

Source to row map (complete):

- A B: B1 001, B2 002, B3 003, B4 004, B5 005, B6 006, B7 007, B8 008, B9 009, B10 010, B11 011, B12 012, B13 013,
  B14 014, B15 014, B16 018, B17 018, B18 020, B19 014, B20 015, B21 014, B22 016, B23 016, B24 017, B25 018,
  B26 019, B27 019, B28 022, B29 023, B30-B33 024, B34 025, B35 026, B36 020, B37 020, B38 021, B39 027,
  B40 065/066/067, B41 068, B42 028/029, B43 030, B44 031, B45 032, B46 033, B47 034, B48 035, B49 036, B50 037,
  B51 038, B52 039, B53 040, B54 041, B55 059.
- A E/W/D/P/O: E1 084, E2 084, E3 085, E4 099, E5 102, E6 089, E7 088, E8 090, E9 103/104, E10 091; W1 042, W2 043,
  W3 044, W4 045, W5 045, W6 067; D1 032, D2 124, D3 053, D4 125, D5 092; P1 109, P2 110, P3 111, P4 112,
  P5 112/113/116, P6 115, P7 119, P8 092, P9 127; O1 092, O2 091.
- A C/A/X/G/DF: C1 047, C2 048, C3 049, C4 050, C5 048, C6 051, C7 151; A1 066, A2 069, A3 066, A4 003, A5 066,
  A6 067, A7 152; X1 046, X2 127, X3 153, X4 154, X5 004/054, X6 155, X7 116/117, X8 156, X9 157; G1 082/128,
  G2 128, G3 083, G4 132, G5 133, G6 134, G7 138, G8 059, G9 070, G10 056, G11 141/150, G12 140; DF1 011, DF2 084,
  DF3 016/099, DF4 038, DF5 045, DF6 152.
- PL: S1 020, S2 004/008/029/043, S3 133, S4 026, D1 133, D2 004, D3 020, D4 015, D5 130, price-drift 052,
  core 078, proof2 008/078, held 143, F1-F5 145.
- MB L: L1 061/140, L2 082/083/128, L3 079/080, L4 060, L5 056/058/059/061, L6 070/072/074/076, L7 004/006/009/094,
  L8 084/086/087/088/095/124, L9 097/100/114/122/123, L10 057/094/104/112/113/117, L11 133, L12 082/095/096/107/148.
- MB B: B1.1 080, B1.2 081, B1.3 142, B1.4 085, B1.5 005, B1.6 008, B1.7 059, B1.8 135, B1.9 134, B1.10 063;
  B2.1 079, B2.2 093, B2.3 105/106, B2.4 124, B2.5 118, B2.6 094, B2.7 095; B3.1 071, B3.2 057, B3.3 114, B3.4 094,
  B3.5 077; B4.1 087, B4.2 137, B4.3 083, B4.4 148, B4.5 058, B4.6 133; B5.1 086, B5.2 084, B5.3 096, B5.4 087,
  B5.5 083; B6.1 084, B6.2 083, B6.3 122, B6.4 096, B6.5 133; B7.1 087, B7.2 148, B7.3 094, B7.4 083, B7.5 152,
  B7.6 059; B8.1 123, B8.2 124, B8.3 117, B8.4 127, B8.5 127, B8.6 061, B8.7 135; B9.1 056/059, B9.2 094, B9.3 083;
  B10.1 059/124, B10.2 094, B10.3 135.
- MB T: T1 085, T2 087, T3 075, T4 086, T5 124, T6 105, T7 060, T8 099, T9 146, T10 074.
- GAPS: AH1 085, AH2 086, AH3 099, AH4 100, AH5 060, AH6 070/075, AH7 074, AH8 087/088, AH9 108, AH10 072;
  G1 128/130, G2 061, G3 112/114/117, G4 148, G5 059, G6a 142, G6b 008, G6c 005, G6d 020, G7 080, G8 123,
  G9 140/141, G10 131/133; LH1 098, LH2 144, LH3 064, LH4 143.
- C2: D1 076, D2 120, D3 106/114, D4 058, D5 062, D6 061.
- C3: M1 100, M2 086, M3 148, M4 082, M5 104, M6 103, M7 064/088, M8 060, M9 122, M10 074/075, M11 117,
  M12 140/141, M13 136, M14 147, M15 005/008.
- C4: §1.1 046, §1.2 047, §1.3 001, §1.4 018, §1.5 024, §1.6 024, §1.7 032, §1.8 091/109, §1.9 120, §1.10 055,
  §1.11 133/136; §2.1 128, §2.2 129, §2.3 131, §2.4 032, §2.5 095/101, §2.6 107; §3.1 058, §3.2 056, §3.3 060,
  §3.4 047, §3.5 057, §3.6 056, §3.7 057; §4.1 070, §4.2 070, §4.3 073, §4.4 018, §4.5 024, §4.6 024, §4.7 024,
  §4.8 018, §4.9 076, §4.10 101/113, §4-p 070; §5.1 082, §5.2 076, §5.3 084/091, §5.4 097/109, §5.5 100,
  §5-p 085/087; §6.1 101, §6.2 057, §6.3 099, §6.4 103/104/131, §6.5 087, §6.6 087, §6.7 107, §6-p 106;
  §7.1 114/115, §7.2 119, §7.3 113, §7.4 120, §7.5 121, §7-p 113; §8.1 139, §8.2 062, §8.3 114, §8.4 056,
  §8.5 082, §8-p 139; P1 061, P2 139, P3 058, P4 070, P5 126, P6 129, P7 086/114, P8 128, P9 148/149.

Deliberate merges (several source items into one row): the four builder money figures into MR-014; the three
ADR-055 strike-placement features asked as one question (MR-004, MR-008, MR-029); all "data before a broker login"
items into MR-059; all auto-trading extras into MR-094; all multi-broker/multi-account items into MR-083; all
history-based charts into MR-066; marketplace, leaderboard and social-proof items into MR-127; the C4 engine
bullets that are already built into MR-018, MR-024 and MR-070. Not counted as items: the gap list's "Top 15" (a
ranking of rows already listed), MB §0-§1 and §5-§6 (method and sources), GAPS §4 (limits), and C4's architecture
flow paragraph (a summary of sections 1-8).

Source corrections found while triaging: C3 M5 and M6 call the kill switch and market hours "built"; both are held
PRs (#463, #455), with 0 hits on `main`. C3 M13 calls data protection "not decided"; REQ-013 and REQ-074 cover it.

## OWNER queue (23 rows; ask in this order)

Answered: every row below was decided in "Owner answers during triage" (Q-1 to Q-19); this list is kept as the order in which they were asked. The Class column above shows the result.

Questions that unblock others come first.

1. MR-130: Phase order, and when multi-user sign-in is built. Unblocks every per-user row (MR-128, MR-129, MR-124, MR-112).
2. MR-004 + MR-008 + MR-029: May the platform place strikes by a fixed, published rule (SPEC CHANGE ADR-055 (1))? Unblocks MR-043 and Learn "Open in Builder".
3. MR-020: Target level and target date what-if (SPEC CHANGE ADR-120 (1)).
4. MR-014: New money figures on the builder summary.
5. MR-015: Show POP.
6. MR-012: Typed entry price per leg.
7. MR-017: Existing positions in the margin figure.
8. MR-112: Where stop-loss and conditional exits live (our alert vs Zerodha's triggers). Unblocks monitoring design (MR-114).
9. MR-124: Paper tracking of a saved plan.
10. MR-140: Hosting, deploy pipeline and staging. Unblocks MR-061 and MR-114.
11. MR-059: Prices before a broker login (data licence).
12. MR-148: Plan B if the basket counts as "algo".
13. MR-150: Product analytics and session replay.
14. MR-067: Events calendar data source.
15. MR-133, MR-134, MR-135: Paid plan, free Pro, other revenue lines (deferred until Q260/Q211; record intent only).
16. MR-137: Read-only access for a mentor or family member.
17. MR-151: Option chain Excel download.
18. MR-157: Support chat and "What's New".
19. MR-155: Video courses.

## Requirements written

Every WRITE, DECIDED or TECH row mapped to the requirement and acceptance criteria that carry it (docs batch 2026-10-21,
REQ-076 to REQ-133 and the amendments for ADR-150 to ADR-164). Rows already covered by an earlier requirement name it;
rows not written say why. REQ-088 was removed (its content is REQ-109). REQ-133 and REQ-119 both touched MR-142: REQ-119
is the complete rule, REQ-133 keeps the live-socket and first-price parts.

| Row | Class | Requirement / AC |
|---|---|---|
| MR-003 | WRITE | REQ-090 |
| MR-004 | WRITE (held) | REQ-079 (held for Q211) |
| MR-005 | DECIDED | REQ-076 (leg stepper, multiplier, leg toggle, shape name); AC-7 whole-strategy Execute is ADR-163 |
| MR-006 | DECIDED | covered by REQ-028 and ADR-143 |
| MR-007 | WRITE | REQ-076 (leg stepper, multiplier, leg toggle, shape name); AC-7 whole-strategy Execute is ADR-163 |
| MR-008 | WRITE | REQ-078 |
| MR-010 | WRITE | REQ-076 (leg stepper, multiplier, leg toggle, shape name); AC-7 whole-strategy Execute is ADR-163 |
| MR-011 | WRITE | REQ-076 (leg stepper, multiplier, leg toggle, shape name); AC-7 whole-strategy Execute is ADR-163 |
| MR-012 | WRITE | REQ-077 |
| MR-013 | WRITE | REQ-080 |
| MR-014 | WRITE | REQ-081 AC-1 to AC-8; AC-9 to AC-11 for % of funds (ADR-164) |
| MR-015 | WRITE (held) | REQ-082 (label held for Q211) |
| MR-017 | WRITE | REQ-081 AC-1 to AC-8; AC-9 to AC-11 for % of funds (ADR-164) |
| MR-019 | WRITE | REQ-083 |
| MR-020 | WRITE | REQ-084 |
| MR-021 | WRITE | REQ-084 |
| MR-022 | WRITE | REQ-083 |
| MR-023 | DECIDED | REQ-083 |
| MR-025 | WRITE | REQ-084 |
| MR-026 | WRITE (held) | REQ-091 (held for display rights) |
| MR-027 | WRITE | REQ-080 |
| MR-028 | WRITE | REQ-080 |
| MR-029 | WRITE (held) | REQ-079 (held for Q211) |
| MR-030 | DECIDED | covered by REQ-030 |
| MR-031 | WRITE | REQ-089 |
| MR-033 | DECIDED | covered by REQ-009 and REQ-038 |
| MR-034 | WRITE | REQ-086 |
| MR-035 | DECIDED | covered by REQ-070 |
| MR-036 | DECIDED | covered by REQ-061 |
| MR-037 | WRITE | REQ-085 |
| MR-042 | DECIDED | covered by REQ-024 and REQ-069 |
| MR-043 | WRITE (held) | REQ-027 AC-1, REQ-079 AC-10 (held for Q211) |
| MR-044 | WRITE | REQ-085 |
| MR-048 | DECIDED | REQ-087 |
| MR-049 | DECIDED | covered by REQ-029 |
| MR-050 | WRITE | REQ-087 |
| MR-051 | DECIDED | covered by REQ-031 |
| MR-052 | WRITE | REQ-077 |
| MR-058 | DECIDED | covered by REQ-052 |
| MR-059 | WRITE (held) | REQ-105 (held for data permission) |
| MR-061 | TECH | REQ-113 |
| MR-062 | TECH | REQ-113 |
| MR-063 | TECH | not written (TECH: JSON is fine) |
| MR-064 | TECH | not written (ADR-091 and ADR-092 decide; the fetch waits on #488) |
| MR-065 | WRITE | REQ-106 |
| MR-066 | WRITE (held) | REQ-107 (held for display rights) |
| MR-067 | WRITE (held) | REQ-108 (held for data licence) |
| MR-068 | WRITE (held) | REQ-107 (held for display rights) |
| MR-069 | WRITE | REQ-108 (held for data licence) |
| MR-077 | TECH | not written (TECH: no need now) |
| MR-078 | TECH | REQ-078 |
| MR-080 | TECH | REQ-117 |
| MR-090 | WRITE | REQ-102 |
| MR-091 | DECIDED | covered by REQ-057 |
| MR-092 | WRITE | REQ-103, REQ-104 |
| MR-095 | TECH | REQ-118 |
| MR-096 | TECH | not written (no inbound API) |
| MR-098 | TECH | not written (open defect, tracked as an issue) |
| MR-102 | DECIDED | covered by REQ-056 |
| MR-103 | DECIDED | covered by REQ-056 |
| MR-104 | DECIDED | covered by REQ-056 |
| MR-109 | DECIDED | covered by REQ-044 |
| MR-112 | WRITE | REQ-100 (AC-1 to AC-10 price-level triggers; AC-11 to AC-16 platform-run P&L stop, ADR-162), REQ-101 (AC-1 to AC-9 triggers; AC-10 to AC-12 platform-run P&L stop); held for static IP, algo standing and Q211 |
| MR-113 | DECIDED | covered by REQ-041 |
| MR-114 | TECH | REQ-115 |
| MR-115 | DECIDED | covered by REQ-043 |
| MR-116 | DECIDED | covered by REQ-042 |
| MR-117 | DECIDED | covered by REQ-062 |
| MR-118 | TECH | REQ-116 |
| MR-119 | DECIDED | covered by ADR-102 and ADR-103 |
| MR-120 | DECIDED | covered by REQ-045 and REQ-046 |
| MR-121 | DECIDED | REQ-112 |
| MR-122 | DECIDED | covered by REQ-060 |
| MR-123 | WRITE | REQ-110 |
| MR-124 | WRITE | REQ-109 |
| MR-125 | WRITE | REQ-111 |
| MR-126 | DECIDED | covered by REQ-038 |
| MR-128 | DECIDED | REQ-125 |
| MR-129 | WRITE | REQ-125 |
| MR-136 | DECIDED | REQ-127 |
| MR-138 | WRITE | REQ-132 |
| MR-141 | TECH | REQ-126 |
| MR-142 | TECH | REQ-119 (complete late-reply rule); REQ-133 keeps the socket-version part |
| MR-144 | TECH | REQ-114 AC-5 and REQ-133 AC-3 (first-price wait) |
| MR-147 | WRITE | REQ-129 |
| MR-150 | WRITE (held) | REQ-130 (held for consent check) |
| MR-151 | WRITE (held) | REQ-131 (held for exchange terms) |
| MR-153 | WRITE | REQ-092, REQ-093, REQ-094 |
| MR-154 | WRITE | REQ-092, REQ-093, REQ-094 |
| MR-155 | WRITE (held) | REQ-096 (held) |
| MR-156 | WRITE | REQ-092, REQ-093, REQ-094 |
| MR-157 | WRITE (held) | REQ-095 (held) |

Retention (no register row of its own): REQ-128. Amended existing requirements: REQ-100, REQ-101 (ADR-162), REQ-081 (ADR-164), REQ-076 (ADR-163 cited).
