# Builder walkthrough: every claimed criterion checked on the running app (2026-10-26)

Owner request 2026-10-26 ~19:45 IST: show each requirement the builder table claims as Done or partial working, criterion
by criterion; note every issue; fix NOTHING until the walkthrough ends. Owner choices: start now (closing prices, real
Zerodha session; moving-price criteria on recorded frames, short live re-check in market hours); depth = every criterion.

Setup: API `127.0.0.1:8765` (APP_ENV=development, LIVE_MARKET=1, DB ofo_dev via `dev_run.py`, main @ 24775939);
screen `127.0.0.1:5173` (vite dev). Kite session owner, started 26 Oct 11:07 IST, expires 27 Oct 06:00 IST. Market
closed (walkthrough began 19:50 IST).

20:08 IST, owner: "I am fine with the last closed price, not live price right now as market is closed but want to see
all features". Harness (scratch, not in the repo): `run_api_closing_prices.py` starts the REAL app and overrides only
`FeedState.market_closed -> False` and the stale limit -> 1 day, so Kite's after-hours snapshot (today's close) reads
as current. Every price seen below is the 26 Oct close fed this way; staleness/market-closed criteria are judged
separately on the plain app.

Verdicts: PASS (seen working), FAIL (claimed, not working), PARTIAL, NOT SHOWN (could not be shown, reason given),
DEFERRED (the table already says deferred: not counted against the claim).

## Issues found (fix after the walkthrough)

| # | REQ / AC | What happened | Severity |
|---|---|---|---|
| I-1 | REQ-079 (held) | Clicking "Bull Call Spread" under Ready-made shapes did nothing; leg list stayed "No legs yet", no message. Held feature is visible and clickable but silent. | to triage |
| I-2 | dev data | Saved list on ofo_dev holds ~14 "E2E 28f history/delete" rows left by e2e runs: e2e writes to the development database. | to triage |
| I-4 | REQ-080 AC-1/2/3 | Leg picker shows NO strikes: "The list of contracts could not be read right now. ATM unknown". `/api/leg-picker/strikes` answers 200 with `reason: CATALOGUE_UNREADABLE`, `rows: []`, while `/api/catalogue/NIFTY/contracts?expiry=2026-10-27` returns the contracts and the same `stored_chain` read run standalone returns 289 rows / 288 permissions. No warning reaches the log. The core picker is unusable on the real app. Also the browser re-requests strikes about once a second (HTTP polling). | CRITICAL |
| I-4 cause | REQ-080, REQ-029/030 | Root cause (read, not yet fixed): `backend/ofo_app/chain_push.py:211` returns `ChainCatalogue(expiries, options, permissions)` but the dataclass's 3rd field is `unreadable` (`permissions` is 4th). The permission dict lands in `unreadable` (truthy) -> every real strikes/chain read says CATALOGUE_UNREADABLE, and permissions stay empty. Introduced by 36c30be4 (W-118-sel). Tests override `get_picker_reader` with a fake, so the real `stored_chain` was never run by any test: the known class "verified on a module the product does not call". Confirmed with market treated as open (still unreadable). | CRITICAL |
| I-5 | product (after hours) | With the market closed the builder shows NO price at all (no last close): every leg "Draft - Live data not connected", money panel "No numbers are shown". By design (ADR-015), but Sensibull shows the last close after hours. Owner wanted to see closing prices: candidate product question, not a defect. | owner question |
| I-6 | REQ-080 AC-6 | NIFTY spot never arrives on the builder (futures reply `SPOT_MISSING`, every "Forward used for pricing" is "-"), even with closing futures prices flowing. Nothing on the builder subscribes the index. | to triage |
| I-7 | REQ-076 (layout) | Leg rows wrap: "Edit"/"Remove" fall onto a second line on every leg at 1536 px. | minor |
| I-8 | REQ-055 | The margin refusal text is printed twice in red, word for word, with three unlabelled (i) icons between them. | major (UX) |
| I-9 | REQ-055/081 wording | "estimated from spot" floats alone on two lines; margin text says "With the premium up to your limit prices" in a builder that places no orders. | minor |
| I-10 | REQ-076 AC-6/AC-8 | With the bought 23200 CE unticked, the label still reads "3 selected - Short Iron Condor" and the left-out leg keeps its Hedge mark; the three legs in the numbers are not an iron condor. Spec unclear whether the name follows ticked legs only. | to triage |
| I-11 | REQ-080 AC-7 | Depth popup columns have no spacing: "179.15181.60325" (bid, ask, ask qty run together). Content correct, unreadable. | major (UX) |
| I-1b | REQ-079 | Cause of I-1: `POST /api/strategies/load-template` answers 422 and the screen shows nothing. | (with I-1) |
| I-3 | navigation | CORRECTED ~20:40: the sub-item /strategies/strategy-builder IS the real builder (screenshot ours/16). Only the section page /strategies (and /home etc.) is a placeholder list of sub-items, so the top menu needs two clicks to reach any screen. Absorbed by the ADR-193 (4) menu rebuild. | minor |
| I-12 | REQ-080 AC-9 | BUY 23 Nov future added from the Futures tab (65 = 1 lot) while the tab showed its LTP 22,889.80, but the leg got NO planned entry ("saved without a planned entry. Reprice it"); Reprice answers 200 and still captures nothing; with that leg present every number disappears ("No numbers are shown"). A future can be added but never priced. | major |

## Per-criterion verdicts

### REQ-080 Leg picker (row 19, claimed Done; live check pending AC-6)
| AC | Verdict | What was seen |
|---|---|---|
| AC-1 | FAIL | Strikes/Futures tabs and the 10/20/30/40 selector exist, but the Strikes tab lists no strikes (I-4). |
| AC-2 | FAIL | No strike rows, so no LTP/OI/IV/delta (I-4). |
| AC-3 | FAIL | No Buy/Sell cells to pick from (I-4). Legs could only be added through the "Add a leg" dropdowns. |
| AC-4 | FAIL | Quantity list lives in the picker rows (I-4). |
| AC-5 | PASS | Plain app, market closed: futures show "-" with "The live feed is not fresh, so no price is shown as current"; a leg added with no price shows "Draft - Live data not connected" + Set price. |
| AC-6 | PARTIAL | Futures 27 Oct / 23 Nov / 29 Dec listed with closing LTP (22,774.80 for 27 Oct); every "Forward used for pricing" is "-" because the spot never arrives (I-6). |
| AC-7 | PASS (UX issue I-11) | Depth for 3 Nov 22700 PE: 5 bid/ask levels with qty, Open 300.00, High 385.95, Low 175.00, Prev close 309.65, last trade 15:39:58, read 20:22:33; only a Close button. |
| AC-8 | pending | Needs the plain (market-closed) app: re-run in the plain-app pass. |
| AC-9 | see below | |

### REQ-076 Leg rows (row 20, claimed Done)
Leg set: NIFTY 3 Nov SELL 22800 CE 234.90, SELL 22700 PE 181.55, BUY 23200 CE 73.25, BUY 22300 PE 74.95 (26 Oct close).
| AC | Verdict | What was seen |
|---|---|---|
| AC-1 | PASS | + on 22800 CE -> 22850 CE (next listed strike). Ends-of-list disable not tried. |
| AC-2 | PASS | 22850 CE re-captured 209.75 at 20:17:08; other three legs kept their entries and times. |
| AC-3 | PASS | Every edit is a server call (8 leg-edit, 5 planned-entry, 4 outcome POSTs); StrategyLegRow.vue header: client-side P&L removed. Hand check: premium 243.10 x 65 = 15,801.50 matches the screen. |
| AC-4 | PASS | Multiplier 3 -> 195 per leg; premium 47,404.50 (x3); max loss 31,033.73 = 78,000 - 47,404.50 + 438.23 charges; Zerodha margin 2,08,924.21 (~3 x 68,007). |
| AC-5 | PASS | Show: Quantity -> 195 = 3 x 65 (lot size from the instrument file). Freeze-limit block not tried (needs > 1,800 qty). |
| AC-6 | PASS (see I-10) | Unticked BUY 23200 CE: row greyed (opacity 0.6), "Left out of the numbers", Max loss "Unlimited", Zerodha margin 4,83,045.96. |
| AC-7 | NOT SHOWN | No Execute button on the builder: order path out of scope (ADR-165). |
| AC-8 | PASS | "Short Iron Condor" with both BUY legs marked Hedge (one wider wing). |
| AC-9 | PASS | BUY 23200 CE edited to BUY 23200 PE -> "Custom Strategy", no Hedge marks, legs unchanged. |
| AC-10 | PARTIAL | Empty: "No legs yet", Add leg, Pick from Option Chain, "No draft strategy is open", no zeros (seen). Steppers/multiplier without live data: not yet tried; plain-app pass. |
| AC-9 (REQ-080) | FAIL | Futures tab Buy on 23 Nov added BUY 23 Nov FUT (65) with no planned entry; Reprice captured nothing (I-12). |

### REQ-077 Entry prices (row 21, claimed Done) - started, paused
| AC | Verdict | What was seen |
|---|---|---|
| AC-2 | PASS (part) | Typed 200.02 on SELL 22850 CE: refused with the four-part message "the price must be a positive multiple of Rs 0.05 ... The typed price was refused and the previous price stays"; entry stayed 209.75. The 0 / negative / text cases not yet tried. |

## PAUSED 2026-10-26 ~20:20 IST (owner)
The owner stopped the walkthrough: the UI does not look like Sensibull. ADR-193 (owner answers ~20:25-20:40): Sensibull
layout for every screen the spec has, our brand; UI study + builder redesign FIRST, folding in I-4 and I-7..I-11; the
walkthrough then RESUMES on the redesigned screen from REQ-077, and its issues are fixed after it.
Checked so far: REQ-080 (9 ACs), REQ-076 (10 ACs), REQ-077 AC-2 part. Not yet: the other 25 claimed requirements.
