# Goal contracts: builder phase (Strategy Builder, strike drawer, Option Chain), 2026-10-27

## Summary (one screen)

**Phase scope (ADR-196 (4), owner answers P1-P9):**
1. Build the Strategy Builder, its strike drawer and the Option Chain screen, laid out like Sensibull, with our rules on top.
2. Four indices (NIFTY, BANKNIFTY, FINNIFTY, SENSEX), no stocks, no order placing (ADR-157, ADR-165).
3. In: Manual P/L (REQ-089, row 39), BANKNIFTY / FINNIFTY (row 46), a read-only Positions tab (REQ-104), and the Tracked tab's live proof (row 53).
4. Placeholder only: the price chart (screen 027) and the strategy chart (REQ-091), each as a "Coming soon" card.
5. Out: the separate feeding screens (Wizard, Easy Options, Draft Portfolios, OI pages, IV chart, straddle charts), the "Add Booked P&L" chart toggle, Share.

**Plan:** 17 short contracts (GC-B1 .. GC-B17), one fresh session each, about 2 rows each. **34 row units** in total,
covering all 77 in-scope gap rows (G-ids). Each gap row sits in exactly one item; the check is the script in the
evidence section.

**Estimate:** 34 rows x 3.5 h = 119 h, plus 25% for review rounds = **about 149 h, or 18.6 working days at 8 h**.
With the memory note's add-ons (migrations, owner answers on new REQs, handovers) it comes to **about 170 h, or 21.3
working days**. Several parts are unmeasured (section 4).

**First three contracts:**
- **GC-B1**: land the four local branches (#582 items 3/7/8, #583 I-1/I-6/I-12, row 33, the pre-push gate) with one
  combined check, one review, one push and the merges; then measure the 5 unmeasured builder and drawer rows.
- **GC-B2**: a leg edit within 1,000 ms at p95 (REQ-078 AC-1, G-019), and Width / Hedge show their values (G-018).
- **GC-B3**: the builder's small fixes. The "..." menu gets Save / Save As / Rename, the saved list shows legs and has
  rename, a Funds Needed row is added, and #582 items 2 and 4 are fixed.

Sources: `spec/decisions/ADR-196.md`, `docs/process/builder-goal-2026-10-27.md`,
`docs/process/builder-gap-list-2026-10-27.md` (100 rows), `docs/process/builder-sequence-2026-10-22.md` (rows 1-63),
`docs/process/goal-chain.md` (chain rules), `docs/process/chunk-session-prompts.md` "Common rules" (they apply to
every contract below and are not repeated). Row time: auto-memory `estimate-from-measured-row-time` (about 3.5 h per row,
measured over check, fix rounds, gate and CI; never build time).

---

## 1. Rules for every contract here

- One contract per fresh session. Start from the newest handover block and run the item rows top to bottom.
  Independent items may run two at a time only where `overlap_gate.py` passes.
- Every item's step 1 is its proof on real input: the live app in market hours (09:15-15:30 IST, owner's cached Kite
  token, `dev_run.py` on `ofo_dev`), or the recorded replay labelled as replay when the market is closed. In the
  second case the live proof is still owed, and the next market-hours contract runs it first.
- Every build brief carries a `Sensibull:` line with the gap row's screen numbers, plus the Common-rules lines.
- "REQ to write first" means the item's step 0 drafts the requirement. That draft is a business call and needs owner
  approval. It goes into `docs/process/owner-questions-<date>.md` with a recommendation, and the session builds the
  other items while it waits (never-wait rule). No code is written before the REQ is approved.
- Defects found outside an item's gap ids become a `deferred` issue (run discipline C4). They do not grow the item.
- At most 2 review rounds per item. A CRITICAL or MAJOR after round 2 on Tier A code parks the item with an issue,
  and the contract moves on.
- **Stop condition (all contracts):** every item is merged on main with CI green, or parked with an issue. Each
  item's proof row is recorded. A handover block (DONE / PENDING / BLOCKED / PARKED / NEXT) is on main, and the next
  contract is marked NEXT. A contract with a live proof that could not run in market hours ends PARTIAL and names the
  owed proof.
- Tiers: A = fresh Opus check (engine, money, live data, Zerodha reads, gates). B = Sonnet check (layout, display).
  C = no review (docs, measurement, spec wording).

## 2. The contracts

### GC-B1: land the four local branches, then measure the unmeasured rows

**Core:** the four local branches, stacked on one integration branch, pass `prepush.py` and CI. On live prices, an
empty builder then shows the NIFTY spot, a ready-made click loads real legs (no 503), and a futures leg gets a planned
entry.
**Proof:** step 1, in market hours, on the integration branch through the product path: read back the empty builder's
spot, the legs loaded by one ready-made click, and the futures leg's planned entry, and record all three. A failing
core stops items 1-5.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Land #582 items 3, 7, 8 (branch `ui/fix-582-drawer-strikes-commas`, cfbec321). It also fixes the decimal part of G-015 / G-074 and the footer-bleed part of G-079; those rows are counted in their own items. | G-036 | #582, REQ-081 | B | Time value prints with separators ("-14,118"); strikes print "22300"; the 21-strike list scrolls above the footer | Built locally, not pushed |
| 2. Land #583 I-1, I-6, I-12 (branch `fix/583-index-lease-futures-entry`, f875baad) | G-007, G-008, G-066, G-082 | #583, REQ-080 AC-6 / AC-9, REQ-079, REQ-072 | A | The core proof above | Built locally, not pushed |
| 3. Land row 33 (branch `build/row-33-chain-values`, 9e4eed68). This branch builds the Details view part of G-093; G-093 is counted in GC-B14. | G-090 | row 33, REQ-029 AC-2 / AC-3 / AC-9 | A | The row-33 brief's core proof: two consecutive live chain pushes read back, and ATM IV against a hand Black-Scholes check | Built locally, not pushed |
| 4. Land the pre-push gate (branch `process/prepush-gate`, e51f20d3). This is the mechanism for `local-ci-mirror-runs-a-subset` (4th occurrence). | none (process item) | runbook, ADR-189 | A | Red then green: a planted ruff-ratchet rise and a stale coverage row each make `prepush.py` fail; clean, it passes | Built locally, not pushed |
| 5. One combined check over items 1-4 (one `prepush.py` run), one Opus review over the whole diff, one fix round, one push, then each merge via `merge.py <pr> --reviewed-sha <full sha>` | (items 1-4) | - | A | CI green on main after the last merge; main proven intact | Not started |
| 6. Measure the unmeasured rows (read-only, Sonnet): per-leg expiry list, untick a leg, a calendar / mixed-expiry strategy, phone width, drawer settings. Each gets a verdict. A row that differs goes by name into the contract that owns its region (B3 for builder rows, B11 for drawer rows), not into a new contract. | G-016, G-017, G-065, G-069, G-083 | REQ-076, REQ-078, REQ-009, REQ-080, REQ-138 | C | A live walk plus Sensibull S-102, S-111, S-104, S-035 and catalogue pass 3; one verdict line per row | Not started |

Rows: 2.0 (landing 1.5, measuring 0.5). Owner needed: once, a Kite login in a private window if no token is cached.
Budget: 420 min wall-clock, 300 tool calls (orchestrator). Each dispatched item carries its own tier budget.
Stop: as section 1. **Next: GC-B2.**

### GC-B2: edit speed and the Width / Hedge values (row 30 remainder)

**Core:** a leg edit's numbers come back within 1,000 ms at the 95th percentile (REQ-078 AC-1; ADR-196 (3) makes it
part of "done").
**Proof:** step 1, before any change: 20 live leg edits on the real app, with the browser and server times of each
read back. Find where the ~2 s goes (#582 item 1 measured planned-entry 4.56 s plus outcome 4.9 s on replay). Fix the
class, then repeat the 20 edits and record the p95.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Leg edit within 1,000 ms at p95 (#560, #582 item 1) | G-019 | row 30, REQ-078 AC-1 | A | The 20-edit timing before and after, p95 at or under 1,000 ms | Not started |
| 2. Width and Hedge show their values between the - / + buttons | G-018 | row 30, REQ-078 | A | On a live short iron condor: "Width 400", "Hedge 200" read back from the screen | Not started |

Rows: 2.0. Owner needed: Kite login if no token is cached. Budget: 420 min wall-clock, 300 tool calls. Stop: as
section 1; row 30 closes when AC-1's live half (#560) passes. **Next: GC-B3.**

### GC-B3: builder fixes (menu, saved list, Funds Needed, #582 leftovers)

**Core:** the "..." menu on an unsaved strategy offers Save, Save As and Rename, and each works through the save path
(REQ-134).
**Proof:** step 1, on the running app: Save As on a 4-leg strategy makes a copy with a new name, rename changes the
name, and both read back from the saved list.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. "..." menu: Save, Save As, Rename (Share stays out, P7) | G-024 | row 29, REQ-134 | B | The core proof | Not started |
| 2. Saved list: a legs line ("NIFTY26OCT22500PE and 3 more"), rename and delete on hover; test rows gone (#583 I-2) | G-028 | row 29, REQ-134, #583 | B | The live list read back next to Sensibull S-117 / S-218 | Not started |
| 3. Funds Needed row in the summary (#537) | G-038 | row 26, REQ-081 | A | A live 4-leg plan's Funds Needed read back against Zerodha's margin reply | Not started |
| 4. #582 item 2 (flaky leg-picker timer tests) and item 4 (the select-all tick needs a server batch edit) | none (#582 items) | REQ-076 | B | Item 2: 5 full Vitest runs green. Item 4: select-all sends one batch edit and the numbers recompute once | Not started |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B4.**

### GC-B4: warnings (row 31, parked) and number format rules

**Core:** a strategy with a futures leg shows the same warnings in the Builder and on Execute. This is the mismatch
that parked row 31 (#558).
**Proof:** step 1: merge main into `build/c4-row-31f`, run the guard tests, and record the merge commit in #558 (run
discipline B1). Then, on live prices, read back an unhedged short strangle with a futures leg in both places.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Unpark row 31: warnings / Insights drawer and "How this trade works" | G-064 | row 31, REQ-085, #558 | A | The core proof, plus Sensibull S-234 wording checked under ADR-003 (facts only) | PARKED (#558) |
| 2. N-1 number format rules (section 3), then apply them: whole rupees or paise per figure, a minus sign on losses, strikes without ".00", no ISO dates in tables | G-015, G-021, G-031 | new row N-1: REQ to write first | B | Builder and drawer figures read back next to Sensibull S-107 / S-032 under the approved REQ | Not started (REQ to write first) |

Rows: 2.0. Owner needed: approve N-1's REQ (queued, never waited on). Budget: 420 min wall-clock, 300 tool calls.
Stop: as section 1. **Next: GC-B5.**

### GC-B5: builder layout gaps and the two placeholders

**Core:** the summary card is short enough that the chart starts on the first screen at 1536 x 864 (G-043; Sensibull
shows it about 270 px from the top).
**Proof:** step 1: measure the summary card's height and the chart's top on the live 4-leg strategy before and after
the change, and record both.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. L-1 builder layout (ADR-193): the empty builder (one "Build a new custom strategy" button and the three right-column placeholders), summary card height, Zoom In / Out instead of From / To, target and date controls only under the chart tabs that use them, and the prices stamp with a Refresh button against the live stream (or a recorded decision that it differs on purpose) | G-006, G-027, G-043, G-053, G-059 | new row L-1, ADR-193, UI study UI-110 / UI-116 | B | Screenshots at 1536 px next to Sensibull S-010 / S-012 / S-107; heights read back | Not started |
| 2. Placeholders: the chart icon opens a "Coming soon: price chart" card (UI-021); the Strategy chart tab shows a "Coming soon" card | G-004, G-058 | REQ-107 (held), REQ-091 (held), rows 60, 61 | B | Both cards seen on the running app | Not started |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B6.**

### GC-B6: what-if and the Greeks panel (row 37 as 37a, then 37b)

**Core:** the engine computes the strategy's P&L at a target index level, a target date and an IV offset, with
strike-wise IV (REQ-084).
**Proof:** step 1: on a real recorded NIFTY chain, the engine's target-date P&L for a 4-leg strategy at three target
levels, against an independent hand Black-Scholes check.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. 37a (server): target level / date / IV what-if, strike-wise IV with an offset for all, target-day futures prices, and Greeks totals with rupee examples | G-060, G-062 | row 37, REQ-084 | A | The core proof, plus the futures price per expiry on the target day read back | Not started (partly built on branch W-127) |
| 2. 37b (screen): target and date sliders with Reset, a Target breakeven, P&L table target columns, a Greeks tab with Decay and the multiply toggles (IV shown as a percent), and the portfolio Greeks panel; mounts the REQ-136 mark for breakeven on the target date | G-033, G-054, G-056, G-057, G-061 | row 37, REQ-084, REQ-136 | A | Live: slider moves change the numbers within 1,000 ms; read back next to Sensibull S-013 / S-015 / S-020 / S-021 | Not started |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B7.**

### GC-B7: payoff and SD tables (row 38), then payoff chart extras (row 36)

**Core:** the payoff table lists P&L at the target date and at expiry for index levels at a chosen interval, from the
same engine call (REQ-137).
**Proof:** step 1: the table at intervals 10 / 25 / 50 / 100 on a real recorded chain; three rows checked against
37a's what-if numbers.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 38: payoff table (interval, target and expiry columns, Show %, current row highlighted) and the SD table; mounts the REQ-136 mark for the expected-move bands | G-055, G-063 | row 38, REQ-137 | A | The core proof; the 1SD / 2SD ranges checked against ATM IV by hand | Not started (not built) |
| 2. Row 36: expiry and target curves together, SD bands, OI bars with an "OI data at" strip, a two-value hover, and the projected P&L badge | G-047, G-048, G-049, G-051, G-052 | row 36, REQ-083 | A | Live: hover values equal the payoff table's row at that level; OI bars equal the chain's OI | Not started (partly built on branch W-127) |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B8.**

### GC-B8: builder settings per user (row 40) and the header (row 41)

**Core:** a builder setting saved by the user is read back after a reload and a new session (REQ-138).
**Proof:** step 1: set Lots to Quantity and Show Manual P&L on, reload the page, and read both back from the server.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 40: settings saved per user (lots / qty, expected-move days, which expiries' OI, include open positions in margin, show manual P&L) and the Funds & Margins gear | G-005, G-040 | row 40, REQ-138, REQ-081 AC-5 / AC-6 | A | The core proof; a migration test on `ofo_dev` only | Not started (not built) |
| 2. Row 41: the header with the day's change and percent and the day's OHLC | G-001 | row 41, REQ-139 | A | Live: change and OHLC read back against Kite's quote for NIFTY | Not started (not built) |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B9.**

### GC-B9: market context strip and Info panel (row 42), then Manual P/L (row 39)

**Core:** ATM IV, PCR, max pain and India VIX are computed once per snapshot from the user's own feed (REQ-106).
**Proof:** step 1: in market hours, one snapshot's four values read back. PCR and max pain are checked against the
same chain by hand, and VIX against Kite's quote.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 42: Info panel with OHLC, expiry, monthly future, ATM, PCR, lot, ATM IV, max pain and VIX (IVP stays held, REQ-107), plus N-4, the REQ-072 AC-1 wording for India VIX | G-003 | row 42, REQ-106, REQ-072 (N-4) | A | The core proof; N-4's spec wording in the same PR (spec-first R4) | Not started (not built) |
| 2. Row 39: Manual P/L, a typed booked amount with a note, on its own labelled line, added to the payoff (P3) | G-025 | row 39, REQ-089 | A | A typed amount moves max profit / loss by exactly that amount and never merges with Zerodha P&L; a migration test on `ofo_dev` only | Not started (not built) |

Rows: 2.0. Owner needed: approve N-4's wording if it changes what a user reads (queued). Budget: 420 min wall-clock,
300 tool calls. Stop: as section 1. **Next: GC-B10.**

### GC-B10: POP, breakeven percent, and an unsaved strategy that survives a reload

**Core:** POP is computed by the engine from today's prices and labelled as a model estimate (REQ-082).
**Proof:** step 1: POP for a real recorded short iron condor, against a hand check of the same model at the same spot
and IV.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 56: POP, built and shown in development, switched off in production until the Q211 legal check | G-035 | row 56, REQ-082 | A | The core proof; the production switch is read back as off | Not started (built, switched off) |
| 2. N-3: breakeven percent from spot beside each breakeven (the percent half of G-033; G-033 is counted in GC-B6) | none (its gap row is counted in GC-B6) | new row N-3: REQ to write first | B | Live: "22811 (-0.7%)" shape read back; percent checked by hand | Not started (REQ to write first) |
| 3. N-2: an unsaved strategy survives a page reload | G-068 | new row N-2: REQ to write first | A | Reload with a 4-leg unsaved strategy; the legs and prices read back the same | Not started (REQ to write first) |

Rows: 2.5. Owner needed: approve N-2 and N-3 (queued). Budget: 525 min wall-clock, 375 tool calls. Stop: as
section 1. **Next: GC-B11.**

### GC-B11: strike drawer gaps

**Core:** the drawer opens on the nearest expiry with its strikes listed, and every value sits in its own column at
520 px (G-070, G-075).
**Proof:** step 1: on live prices, open the drawer and read back the expiry and the first 3 strike rows' cells, one
value per cell, next to Sensibull S-032.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. L-2 drawer layout (ADR-193): opening state, header (underlying with change, using row 41), one IV column and OI bars, columns that fit, footer and the last row clear of it, the picked-legs list and the old contract form removed, and a "Show Editor" edge tab | G-070, G-071, G-074, G-075, G-079, G-080, G-081 | new row L-2, ADR-193, REQ-080, UI study UI-200 / UI-202 / UI-206 | B | The core proof, plus a 1536 px screenshot next to S-032 | Not started |
| 2. The strikes reply carries Zerodha's permission, so the drawer disables B / S for contracts Zerodha has not confirmed (#582 item 5) | G-084 | REQ-030 AC-16 | A | A real recorded contract without permission shows B / S disabled; the execution gate still refuses it | Not started |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B12.**

### GC-B12: ready-made shapes and quick picks (row 55)

**Core:** one click on a ready-made card loads real legs at the fixed-rule strikes (REQ-079; the 503 itself was
fixed in GC-B1).
**Proof:** step 1: on live prices, each of the 8 Neutral shapes loads, and its legs are read back against the rule.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 55: cards with a mini payoff icon, Sensibull's groups (Neutral = 8 shapes), and Straddles / Strangles as drawer tabs with Quick Select and the change-type confirm. Built and shown in development, switched on in production after Q211 | G-009, G-010, G-012, G-072, G-073 | row 55, REQ-079, REQ-028, UI study UI-111 / UI-201 | B | The core proof, plus the drawer tabs next to S-036 / S-037 / S-038 | Not started (built, switched off) |

Rows: 1.5. Budget: 315 min wall-clock, 225 tool calls. Stop: as section 1. **Next: GC-B13.**

### GC-B13: pick legs from the chain (row 34) and the chain's live preview (row 35)

**Core:** legs picked on the Option Chain land in the builder's strategy without losing the strategy being built
(REQ-030; #582 item 6).
**Proof:** step 1: with a 2-leg strategy open, pick one more leg on the chain, go back, and read back all three legs
and their planned entries.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 34: B / S on row hover beside the required checkboxes, the Selected Legs panel, "Add Selected", and the drawer footer's "Pick from Option Chain" that keeps the strategy (#582 item 6). No lightning button (ADR-002) | G-096, G-097 | row 34, REQ-030, REQ-029 AC-5 / AC-10 | B | The core proof | Not started (partly built, PR #509) |
| 2. Row 35: live strategy preview on the chain (net premium, max profit / loss, breakevens, mini payoff) from the engine | G-098 | row 35, REQ-031 | A | Live: the preview's numbers equal the builder's for the same legs | Not started (partly built, PR #509) |

Rows: 2.0. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1. **Next: GC-B14.**

### GC-B14: chain display options (row 45) and the chain's Sensibull layout

**Core:** the chain's Change column is filled from a real previous close (F-47; it shows "-" in every cell today).
**Proof:** step 1: in market hours, 3 strikes' change read back against Kite's quote for the same contracts.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 45: ITM shading, the LTP / Greeks / All columns views with column menus (the Details view from row 33 is reused), settings (lots / qty, strikes around ATM, 100 multiples), and the Per Lot toggle | G-092, G-093, G-094, G-095 | row 45, REQ-087, REQ-029 AC-3 | B | Each view and setting read back next to S-061 / S-062 / S-063 / S-067 | Not started (partly built, PR #509) |
| 2. L-3 chain layout (ADR-193): one header strip (underlying with change, expiry, futures price, VIX from row 42, per lot; IVP stays held), expiry list with days, OI in lakh with bars and OI change percent, a filled Change column, and first data on open timed against the target | G-085, G-086, G-088, G-089, G-091 | new row L-3, REQ-029 AC-2 / AC-4 / AC-8, UI study UI-210..UI-214 | A | The core proof, plus the open time measured 5 times and a 1536 px screenshot next to S-060 / S-066 | Not started |

Rows: 2.5. Budget: 525 min wall-clock, 375 tool calls. Stop: as section 1. **Next: GC-B15.**

### GC-B15: BANKNIFTY and FINNIFTY (row 46)

**Core:** every per-underlying value for BANKNIFTY and FINNIFTY (lot size, strike step, expiries) comes from the
exchange files, and a weekly-only shape is refused on a monthly-only underlying (REQ-090).
**Proof:** step 1: on today's instrument files, the four indices' lot size, step and expiry list read back against the
exchange file rows; then one live BANKNIFTY chain push.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. Row 46: four indices in the builder select and on the chain (also closes REQ-001 AC-1) | G-002, G-087 | row 46, REQ-090, REQ-001 AC-1 | A | The core proof, plus a FINNIFTY 2-leg strategy built live in the builder | Not started (not built) |

Rows: 1.0. Budget: 210 min wall-clock, 150 tool calls. Stop: as section 1. **Next: GC-B16.**

### GC-B16: Positions tab, list and grouping (REQ-104)

**Core:** "Import from Zerodha" reads positions fresh and lists only what is not already a strategy's own fills
(REQ-104 AC-1).
**Proof:** step 1: in market hours, on the owner's real account, read only, the importable list read back against Kite's
positions page (example in AC-1: 130 held, 65 owned by strategy 9, so 65 listed). No order call is reachable.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. P-1: Positions tab lists Zerodha positions, read only, with every answer state (stated, empty, failed, unsupported, ambiguous, no session) | G-029 | new row P-1, REQ-104 AC-1 / AC-4 / AC-5 / AC-7, REQ-044, REQ-061 | A | The core proof, plus each answer state shown by a test built from a real recorded reply | Not started |
| 2. P-2: group ticked positions into a new or existing strategy, never attached without the user, with each choice audited. Technical call at brief time, to be recorded: AC-3's "reconciled at once (REQ-060)" is order-path scope deferred elsewhere (as REQ-015 AC-5), so either a read-only reconcile is built or that part is deferred by name | none (P-2 has no gap row) | new row P-2, REQ-104 AC-2 / AC-3 / AC-6 | A | Attach one real position; Zerodha's average price kept exactly (ADR-126); one timeline event read back | Not started |

Rows: 2.0. Owner needed: Kite login in market hours. Budget: 420 min wall-clock, 300 tool calls. Stop: as section 1.
**Next: GC-B17.**

### GC-B17: load positions into the builder, the Tracked proof, and the phase walk

**Core:** ticked positions load into the builder as legs with Zerodha's average price as entry, only when the user
ticks them.
**Proof:** step 1: in market hours, tick one real position and read back the builder's leg and entry against Kite.

| Item | Gap ids | REQ / row | Tier | Proof | Status |
|---|---|---|---|---|---|
| 1. P-3: load ticked positions into the builder | none (P-3 has no gap row) | new row P-3: REQ to write first (REQ-104 has no builder-load AC; nearest REQ-104, REQ-044) | A | The core proof | Not started (REQ to write first) |
| 2. Row 53: the Tracked tab's live proof (P9) | G-030 | row 53, REQ-109 | A | Paper P&L since save read back against a hand calculation on live prices | Not started (merged; live proof pending) |
| 3. Phase close: the whole gap list walked live, every in-scope row re-verdicted "matches" or named, and edits at 1,000 ms p95 re-measured (ADR-196 (3)); a handover for the next phase | (all) | ADR-196 (3) | C | A re-verdicted copy of the gap list with the screenshot names and the timing | Not started |

Rows: 2.5. Owner needed: approve P-3's REQ (queued), and a Kite login. Budget: 525 min wall-clock, 375 tool calls.
Stop: as section 1, plus the phase handover. **Next: the next phase (owner chooses the order, ADR-196 (4)).**

### Out of this phase (listed once)

| Gap id | What | Excluded by |
|---|---|---|
| G-023 | Trade All and Add to Drafts | ADR-196 (2) (ADR-165, no order placing) and (4) (Draft Portfolios next phase) |
| G-032 | Plain sentences under the figures | ADR-196 (2): our requirement (REQ-034 AC-7) stays on top of the layout |
| G-041 | Margin shortfall shown and blocking | ADR-196 (2): ADR-152 safety exception |
| G-046 | "Add Booked P&L" chart toggle (screen 012) | ADR-196 (4): out of this phase (P6) |
| G-099 | Chain footer "Open with OI / IV / Live Charts" (their target pages, and REQ-107 for their data) | ADR-196 (4): OI pages, IV chart and charts are next phase |
| G-100 | Download as Excel | Not an ADR-196 exclusion: the gap list's n-a verdict (REQ-131 Draft, held) |
| Parts of in-scope rows | IVP in G-003 / G-085; Share in G-024; the real price chart behind G-004; lightning in G-096 | ADR-196 (4) (IVP held by REQ-107, Share out, price chart placeholder only) and (2) (ADR-002) |

## 3. New rows the owner's answers created (no builder-sequence row yet)

| Proposed row | Name | REQ | Gap ids | Contract |
|---|---|---|---|---|
| N-1 | Number format rules for the builder and drawer (whole rupees vs paise, minus sign on losses, strikes without ".00", no ISO dates) | REQ to write first | G-015, G-021, G-031 | GC-B4 |
| N-2 | An unsaved strategy survives a page reload | REQ to write first | G-068 | GC-B10 |
| N-3 | Breakeven percent from spot beside each breakeven | REQ to write first (UI-116 waits on a server field) | percent half of G-033 | GC-B10 |
| N-4 | REQ-072 AC-1 wording extended to India VIX (today: "two index rows only (NIFTY 50, SENSEX)") | REQ-072 (existing; a wording change) | part of G-003 | GC-B9, with row 42 |
| P-1 | Positions tab: list Zerodha positions, read only | REQ-104 AC-1, AC-4, AC-5, AC-7 (existing) | G-029 | GC-B16 |
| P-2 | Group ticked positions into a strategy | REQ-104 AC-2, AC-3, AC-6 (existing) | none | GC-B16 |
| P-3 | Load ticked positions into the builder | REQ to write first | none | GC-B17 |
| L-1 / L-2 / L-3 | Layout rows for the builder, drawer and chain | none needed (ADR-193 layout, UI study ids) | as in GC-B5 / B11 / B14 | GC-B5, GC-B11, GC-B14 |

Not made a row: the chain footer buttons (G-099). Their target pages are next phase.

## 4. Estimate

Row time: 3.5 h per row as measured in chunk 3 (check, fix rounds, gate, CI). That figure already includes 1-2 review
rounds, so the extra 25% asked for here works as a buffer on top, not as the review time itself.

| Contract | Rows | x 3.5 h | + 25% | Working days (8 h) |
|---|---|---|---|---|
| GC-B1 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B2 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B3 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B4 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B5 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B6 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B7 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B8 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B9 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B10 | 2.5 | 8.75 | 10.94 | 1.37 |
| GC-B11 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B12 | 1.5 | 5.25 | 6.56 | 0.82 |
| GC-B13 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B14 | 2.5 | 8.75 | 10.94 | 1.37 |
| GC-B15 | 1.0 | 3.5 | 4.38 | 0.55 |
| GC-B16 | 2.0 | 7.0 | 8.75 | 1.09 |
| GC-B17 | 2.5 | 8.75 | 10.94 | 1.37 |
| **Total** | **34.0** | **119.0** | **148.75** | **18.6** |

Add-ons from the memory note:
- Likely migrations: rows 40 and 39, and P-2. That is +1.5 h each, 4.5 h.
- Owner answers on new REQs: N-1, N-2, N-3, P-3. That is +1 h each, 4 h.
- Handovers: 17 x 0.5 h = 8.5 h.

These come to 17 h, or 21.25 h with the 25%. **The total with add-ons is about 170 h, or 21.3 working days.**

Unmeasured, so the estimate can be wrong in these places:
- The 3.5 h figure was measured on REQ rows only. Bundled fix and layout items (GC-B3, L-1, L-2, L-3) and the
  four-branch landing in GC-B1 have no measured time yet.
- The "row units" for bundles (0.5 or 1.5) are judgements, not measurements.
- Live proofs need market hours and the owner's Kite token. A contract that misses the window waits a market day,
  and no day count includes that wait or market holidays.
- GC-B2's speed fix: the cause is not yet found, so its size is unknown until step 1 measures it.
- Parked row 31 (GC-B4) and the four "REQ to write first" items depend on the round outcome and the owner's approval
  time.
- Re-measure after GC-B2 from `gh pr list --state merged --json mergedAt` and update this table.
