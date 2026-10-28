# Goal contract GC-BM: the builder's must-have set, then a user-style test until clean (2026-10-27)

Written 2026-10-27 15:48 IST. Branch `build/gcbm-must-have`, worktree `D:\Abhay\Ventures\OptionsForOptions2-gcbm`
(local only, not pushed). Runs BEFORE GC-B2 and takes its rows out of GC-B3, GC-B6 and GC-B11
(`docs/process/goal-contracts-builder-phase-2026-10-27.md`). Those contracts keep their other rows.

## Owner decisions behind this contract (question tool, 2026-10-27 ~15:20-15:45 IST)

1. Scope: **Strategy Builder + its strike drawer** (gap rows G-001..G-084, G-101). The Option Chain stays in the
   ADR-196 (4) phase but is not in this contract.
2. "Not built" = **missing rows + broken rows** (an error, no result, or a control that does nothing). Rows that only look
   different from Sensibull count as built for this contract.
3. Process: the owner confirms the list once, then this goal contract runs to the end. **No CI, local or GitHub,
   until everything is built and tested** (owner: "Do not run any CI until everything is built and tested").
4. Must-have list confirmed: **G-065, G-075, G-070, G-024, G-051** ("Confirm the 5").
5. Done means: open the screen as a user and test every built feature. Fix **every functional issue** found anywhere on
   the builder or drawer (it errors, shows a wrong number, does nothing, or cannot be read), comparing with Sensibull,
   and repeat the test until a full pass is clean. Purely visual differences go into a list for the owner and are not
   fixed here ("All functional bugs").

Spec basis: ADR-196 (3)/(4) (phase scope; done = matches, walked live), ADR-165 (no order placing), ADR-157 (indices
only), ADR-152 (safety exceptions stay), REQ-076, REQ-078, REQ-080, REQ-083, REQ-134, ADR-143 (mixed expiry), ADR-192
(Save As name). Sensibull: private study `D:\Abhay\Ventures\competitors\sensibull\2026-10-21` (S-010, S-012, S-032,
S-104, S-107, S-115, S-122; `catalogue-raw.md`). Never copy its images into this repo.

**Core:** the basic user loop works on the live builder: pick an index, add legs (drawer and ready-made), edit them
(mixed expiry included), read every summary number, read the chart and its hover values, save / Save As / rename /
reopen / delete.
**Proof:** step 1 below, a recorded user walk of that loop on the live app BEFORE any code, listing every failure.

## No-CI rules (owner instruction 3 overrides chunk-session Common rule 1 for this contract)

- **No push, no PR, no draft PR** until the stop step. GitHub Actions runs on push and on PR only, so nothing runs.
- **No `ci_local.py`, `prepush.py`, `land.py` or `merge.py`** per item. Builders run only the tests of the files they
  touch, plus `ruff` on touched Python files and `npx eslint` on touched frontend files. Briefs say this in place of
  Common rule 1. Long output goes to a log file; read only the tail.
- All work is stacked commits on `build/gcbm-must-have`. Builder sub-branches merge into it locally.
- **One** full pass at the end (step 9). It covers what CI runs that the local gate misses (#587): openapi drift,
  Playwright e2e for the changed pages, then `prepush.py` with the app servers STOPPED (memory killed a run on
  2026-10-27). Then one push, one PR and one CI run.
- No closing keywords ("Fix #586") in commit subjects; `land.py` refuses them.

## Items

| Step | Gap / item | What | Tier | Proof (read back on the live screen) | Status |
|---|---|---|---|---|---|
| 0 | setup | `npm ci` in the worktree's `frontend/` (the junction helper found no modules on 2026-10-27; use a real install, never a junction). Merge local branch `build/c3-small-f2-f5` (4 commits, #537 F2 + ADR-192 Save As pre-fill, not on main; it touches `SaveDraftBar.vue` / `saveDraft.js`, the same files as step 5) and run its tests: `save-draft.test.js`, `draft-link.test.js`, `tests/execution/test_margin_gate.py`, `tests/execution/test_safety_checks.py` | C | Tests green, merge commit recorded here | DONE 15:54: merge `dd21ee32`; pytest 249 passed, vitest 67 passed; `npm ci` exit 0 |
| 1 | core proof | User walk 1 (the U-list below) on the live app, before any change. Each U-step gets pass / FAIL with what was seen and a screenshot name. FAILs that are functional become rows F-1, F-2 ... in the "Found in the walk" table | C | The walk table filled in | PARTIAL 16:41: walk 1 ran on the CLOSING-PRICE launcher (market closed at 15:30; LIVE_MARKET=1, ofo_dev, owner token), not live; 32 U-steps done, findings below; the LIVE walk is owed at 09:15 on 2026-10-28 |
| 2 | G-065 (#586) | Moving one leg to another expiry answers instead of a 500: the summary and chart stay, the leg shows "9 Nov (13 days)" not "2026-11-09", Width / Hedge disabled with a reason, label and curve per ADR-143 (Sensibull S-104) | A | Live 4-leg NIFTY condor, leg 4 moved to the next expiry: numbers and chart shown, no ERR- code | BUILT (closing prices) 16:34: `9cc45079`+`715930c2`+`0cc230e4`; 5 red outcome-route tests first; live: leg 4 -> "9 Nov (13 days)", no 500, Max profit/loss "Not available" + ADR-143 line, Width/Hedge "need one expiry", At Expiry chart shows the reason (f10-after.png); futures-on-another-expiry case in tests; live re-check owed |
| 3 | G-070 | The drawer opens on the nearest expiry with its strikes listed (S-032) | B | Open Add/Edit: expiry chosen, ATM rows visible, no "Choose an expiry" text | BUILT (closing prices) 16:47: `56a4766f`; 2 red then 78 green (leg-picker.test.js); live: drawer opens with an expiry and 21 rows; live re-check owed |
| 4 | G-075 | Every drawer value sits in its own column at 520 px: no run-together cells, Put LTP not cut (S-032) | B | First 3 strike rows read cell by cell, one value per cell; screenshot next to S-032 | BUILT (closing prices): `56a4766f`+`a78cb621` (round 2: OI column cut); live check `g075-check.cjs` -> `bad 0`, 21 rows in LTP/OI/Greeks; live re-check owed |
| 5 | G-024 | The "..." menu offers Save, Save As and Rename and each works (REQ-134, ADR-192; Share stays out, ADR-196 (4)); on an unsaved strategy, only the items that apply, never an empty menu (S-023, S-115) | B | Save As on a 4-leg strategy makes a named copy, Rename changes the name, both read back from the Saved tab | BUILT (closing prices): `4cdda540`; red run by orchestrator (3 new tests fail on old code), 94 green; live: Save As -> copy 36 "GCBM walk condo copy" (ADR-192 pre-fill), Rename -> "GCBM renamed", both read back; empty builder: button disabled |
| 6 | G-051 | Hovering the payoff chart shows the price, its % from spot and the P&L at that price (REQ-083; S-122) | A (P&L number from the one engine, ADR-008) | Hover at 3 x positions; each tooltip's P&L equals the payoff-table value at that level | BUILT (closing prices): `27e8f138` (11 red) `2cb913a2` `96a219a3`; live hover 21,900 (-3.7%) -Rs 3,383.25 / 22,700 (-0.2%) Rs 6,366.75 / 23,500 (+3.3%) -Rs 3,383.25 = payoff table rows; one P&L line only (both curves need REQ-083 AC-1, not built) |
| 7 | F-rows | Fix every functional failure from walk 1, one class at a time (RCA, failing test first, class fix) | per row | Each F-row's U-step passes on the live screen | DONE on closing prices: F-1, F-8, F-10, F-11, F-12 fixed; F-2 / F-3 owed in the live walk |
| 8 | user walk 2..n | Repeat the FULL U-list after the fixes. A new functional failure becomes an F-row and goes back to step 7. Stop when one full pass has zero functional FAILs | C | A clean walk table, timestamped, with screenshots | DONE 19:21: walk 3 (real app, after hours) found F-18; walk 4 (real app, after hours, ADR-200 (5)) CLEAN, U-1..U-32 |
| 9 | final gate | `python scripts/generate_openapi.py` drift check; Playwright for the changed pages (`npx playwright test <specs>`, servers per runbook, stopped after); `python scripts/ruff_ratchet.py`; `python scripts/orchestrator/coverage.py . --check`; then `python scripts/orchestrator/prepush.py` with app servers stopped. One combined review: fresh Opus for steps 2 and 6 and any Tier A F-row, Sonnet for the rest, at most 2 rounds. Then ONE push, ONE PR (Spec-deviation block, no closing keywords), CI, `merge.py <pr> --reviewed-sha <sha>` | A/B | Every command's tail line; CI green on the PR sha; main has the files | IN PROGRESS: review round 1 on 6dbc3920 done early (code does not need market hours): Tier A (Opus) PASS - attacks (b) strike columns never reach the scenario table, (c) mixed expiry COMPUTED with no invented figure, (d) 12 same-expiry runs main vs branch: no number moved, outcome route 25 passed; 2 MINOR: tooltip % computed in the browser from two index levels (accepted, not money), ADR-008 scan skips PayoffChart.vue entirely (pre-existing gap -> deferred issue at step 10). Tier B (Sonnet) PASS, 189 tests + eslint; 5 MINOR, 1-4 accepted as F-13 (menu disabled for a saved strategy with a not-live leg; drawer skips the open-time price read on the Futures tab; one strikes read per page load while shut; stale-reply test never reaches its guard), 5 rejected (display-format has its own raw-ISO tests). The first two review attempts were stopped by the orchestrator by mistake after 2-3 tool calls (see memory check-activity-before-stopping-agent). Push / PR / CI / merge wait for a clean LIVE walk |
| 10 | handover | Gap list re-verdicts for the touched rows, the visual-differences list for the owner, a handover block (DONE / PENDING / BLOCKED / PARKED / NEXT), GC-B2 marked NEXT. These docs ride in the same PR as step 9 (no second push) | C | Files in the PR | Not started |

## The user walk (U-list): every built builder and drawer feature

Run it as a user would, in the browser (Playwright MCP or Chrome), at 1536 x 864, on the live app
(`dev_run.py`, `ofo_dev`, the owner's cached Kite token, market hours 09:15-15:30 IST). Read only: never press an
order button, never call an order endpoint (ADR-165; memory "no clicks inside order panels"). For each step, compare
with the Sensibull screen named and write pass / FAIL / visual-only.

| U | Feature | Do | Expect | Sensibull |
|---|---|---|---|---|
| U-1 | Open the builder empty | Open `/strategies/strategy-builder` | Loads with no console error; spot shows before any leg | S-010 |
| U-2 | Underlying | Switch NIFTY -> SENSEX -> NIFTY | Spot changes; with legs, it asks first (ADR-152) | S-107 |
| U-3 | Ready-made | Click 3 cards (Short Iron Condor, Bull Call Spread, Short Straddle), each on an empty builder | Real legs load at ATM within a few seconds, no 503 | S-011 |
| U-4 | Quick picks | Straddle, Strangle 100 | Legs load | S-037, S-038 |
| U-5 | Drawer open | Add/Edit | Nearest expiry, strikes listed (step 3) | S-032 |
| U-6 | Drawer read | Read LTP, OI and Greeks views | One value per cell, nothing cut (step 4) | S-032, S-033 |
| U-7 | Drawer pick | Pick 4 legs B/S, change lots, Done | 4 legs in the builder with the right side, strike and lots | S-032 |
| U-8 | Futures leg | Futures tab, add a future | It gets a planned entry; numbers stay | S-034, S-233 |
| U-9 | Leg edits | Strike - / +, B/S flip, CE/PE flip, lots change, delete a leg | Numbers recompute each time; no error | S-107 |
| U-10 | Untick a leg | Untick, then tick again | "3 selected", numbers left out, then back | S-111 |
| U-11 | Shift / Width / Hedge | Use each button | The strategy moves as labelled | S-108..S-110 |
| U-12 | Mixed expiry | Move one leg to the next expiry (step 2) | Numbers and chart stay | S-104 |
| U-13 | Multiplier | 1 -> 2 -> 1 | Every figure doubles, then returns | S-103 |
| U-14 | Reset prices | Reset Prices | Entry prices back to now | S-107 |
| U-15 | Summary figures | Read net premium, max profit / loss, breakevens, reward/risk, time and intrinsic value, margin needed / available | Every figure present and consistent with the payoff table (max profit = table's best row, breakeven = table's 0-P&L) | S-107, S-124..S-129, S-241 |
| U-16 | Charges | Open Charges | Breakdown adds up to the total | S-022 |
| U-17 | "?" help | Open every info icon | Each shows its text | S-124..S-129 |
| U-18 | Depth | Open market depth on a leg | OHLC + 5 levels | S-024 |
| U-19 | Payoff chart | At Expiry and Estimated Now; zoom range | Curve draws; spot marker right | S-012 |
| U-20 | Chart hover | Hover 3 points (step 6) | Price, % and P&L shown, equal to the table | S-122 |
| U-21 | Payoff table | Read it | Rows per interval, current row marked | S-017 |
| U-22 | P&L table | Compact and Full table | Per-leg entry, LTP, P&L; totals add up | S-014 |
| U-23 | Greeks | Read the tab | Per-leg and total; values readable (note IV format as visual-only unless misleading) | S-015 |
| U-24 | Settings | Lots / Quantity switch | Every leg shows the chosen unit | S-025 |
| U-25 | Save | Save a 4-leg strategy with a name | It appears in the Saved tab | S-023 |
| U-26 | "..." menu | Save As, Rename (step 5) | Copy and rename read back | S-023, S-115 |
| U-27 | Reopen | Open the saved one from the Saved tab | Same legs and numbers come back | S-117 |
| U-28 | Delete | Delete the copy | Gone from the list; the original stays | S-218 |
| U-29 | Clear all | Clear all | Empty builder, no error | S-107 |
| U-30 | Margin shortfall | A strategy above available funds | The red block shows (on purpose, ADR-152) | S-039 |
| U-31 | Positions / Tracked tabs | Open each | Loads with no error (their full features are GC-B16 / GC-B17) | S-118, S-119 |
| U-32 | Console | Read the browser console after the walk | No uncaught error, no failed API call except ones explained | - |

## Found in the walk (filled in by steps 1 and 8)

| F | U-step | What failed (seen) | Functional or visual-only | Class / RCA | Fix commit | Re-test |
|---|---|---|---|---|---|---|
| F-1 | U-3, U-4 | Ready-made cards and quick picks load legs with NO planned entry: every leg "Draft - Live data not connected", no numbers until Reset Prices (16:00-16:05, u03-condor-3nov.png) | functional | load-template / quick-pick replies carry no entry and ReadyMadePanel emits them unpriced; the drawer and Create Strategy paths capture. Class: every server-placed-shape path (template, quick pick, Learn ?template=) | `d5ab7e46` (6 new tests, red first) + `3e0dc729` (2 ready-made assertions G-065 left on raw ISO, REQ-148 AC-2) | PASS (closing prices) 16:47: condor loads priced in 4.0 s, entries 126.90/166.00/136.60/101.05, max profit 4,581.68, no "not connected" line (f1-after.png); live re-check owed |
| F-2 | U-3 | Once, after Clear all + expiry change + a template load, the 4 leg rows showed no expiry/strike/type and "Updating the numbers..." stayed (16:28 IST, u03-condor-3nov.png) | functional | not reproduced in 6 later loads nor in 3 exact replays of walk 1's steps (18:00-18:04, closing prices); since F-1 the legs arrive only after capture, so the path that showed it is gone | - | re-test once in the live walk; park if absent |
| F-3 | U-5, U-12 | Drawer "Reading strikes..." for ~30 s with 10+ identical GET /api/leg-picker/strikes requests (16:07) | functional if it repeats live | the repeated reads are the designed 5 s refresh while the drawer is open (legPicker.js PICKER_REFRESH_MS = 5000, W-195), not a loop; the 30 s first read did not repeat (883 ms at 18:00, closing prices) | - | time the first read in the live walk |
| F-5 | U-8 | 6 options on 3 Nov + a 23 Nov future -> outcome and leg-edit HTTP 500 ERR-EBE20DBE, MultiExpiryError (16:09) | functional | same class as G-065 (any legs on >1 expiry, futures included) | G-065 `9cc45079` (test added) | owed (live) |
| F-8 | U-19, U-21 | Payoff graph points are a 100-point grid + spot + breakevens, never the strikes: at 22,650 the line reads ~Rs 4,700, true at-expiry P&L Rs 6,366.75; Estimated line breaks at zero crossings (u19-chart.png, u19-estimated.png) | functional (wrong number on screen) | levels.py build_level_set feeds the graph without strikes; table columns Q33D = C stay | `95d050f0` (6 red) `ee96ed82` `5ee5e892` `9dccc01e` (round 2: docs/api/outcome.openapi.json was not regenerated) | PASS (closing prices) 17:00: line kinks at 22550/22650/22850/22950, one continuous line; hover at 22,650.00 Rs 4,852.25 (was a straight-line corner); f8-after.png; live re-check owed |
| F-11 | (integration) | Full vitest after merging F-8: the ADR-008 no-client-maths scan fails on lib/payoffRegions.js (`Math.max/min` gradient clamp), 1 failed / 1175 passed | functional (a guard red) | pixel geometry put outside the named drawing file PayoffChart.vue; fix moves it, scan unchanged | `cb38ef97` (gradient maths moved into PayoffChart.vue, the named drawing exception; scan unchanged; mutation: a Math.max put back turns the scan red) | PASS: full vitest 74 files / 1176 tests green after the merge |
| F-12 | U-5, U-7 (walk 2) | Strangle on 3 Nov, then Add/Edit: the drawer opened on 2026-10-27 (picked at page load with no legs) and 4 picks landed on 27 Oct, making the strategy mixed-expiry by accident (17:08) | functional | LegPicker loadExpiries ran once at mount; the open watcher reloaded only when the list was empty (G-070 round 1 test mounted with legs already present). G-070 round 2 | `4fbb8c5e` (2 red, 83 green) | PASS (closing prices) 17:10: strangle on 3 Nov -> drawer on 2026-11-03, 21 rows, picks on 3 Nov; full vitest 1181/1181 |
| F-13 | (review round 1, Tier B) | MINOR 1-4 above | functional (1, 3); efficiency (4); test gap (2) | see review line in step 9 | `25297a6d` `ecc34f7f` `e4f86b82` (each red first; guard mutation turns the stale-reply test red) | unit: full vitest 1187/1187 after the merge; live re-check in walk 3 |
| F-14 | (review note, checked) | SENSEX straddle (29 Oct 73600 CE/PE) -> Add/Edit: drawer `underlying=NIFTY disabled=true expiry=2026-10-27`, NIFTY strikes 22250/22300 listed - a pick would add a NIFTY leg to a SENSEX strategy (18:00, f14-sensex.png) | functional | LegPicker.vue:50 sets the underlying once at mount; :68 locks it while legs exist (same class as F-12: state decided at mount) | `e6fb17fb` (2 red, 5 new tests; pageUnderlying prop from the page) | PASS (closing prices): SENSEX straddle -> drawer SENSEX, 2026-10-29, 21 rows from 72600; full vitest 1196/1196 |
| F-15 | (Tier A review MINOR 2) | The ADR-008 no-client-maths scan skips PayoffChart.vue and PnLCell.vue entirely | detection gap | whole-file exception instead of named lines | `106178ba` (both files scanned line by line, 21 named uses each with a reason, each must appear exactly once; mutations `Number(point.pnl) * 2`, `p.pnl.toFixed(2)`, `pnl / 2` and a marked-but-unlisted line all fail the scan) | PASS: full vitest 1196/1196 |
| F-16 | (owner question) | After the close on an expiry day every default expiry is the expired one (ready-made, drawer, ?template=) | functional (owner decision ADR-199: roll to next) | default chosen in the browser by list position; the expiries reply now carries `default_expiry` (today skipped at or after 15:30 IST on its expiry day) | `91cae27b` (3 red route tests first; openapi regenerated, drift test passes) | unit: full vitest 1199/1200 + landing.test.js alone 9/9 (the one timeout was load from a concurrent builder); live check after F-17 |
| F-17 | (owner, ADR-200) | Outside market hours the real app shows no prices at all (index "unavailable", legs "Draft - Live data not connected", no summary/chart; 15:58 IST) while REQ-105 AC-4 / REQ-114 AC-7 say the last close is shown labelled | functional (approved requirement not met) | to be measured: the closed-market state makes every quote unhealthy for pricing | `516fc2dd` `11ee7cef` `5eeafea9` (5 red route tests first; order-gate mutation caught) | PASS LIVE 18:55 on the real app, NO launcher: condor priced from the last close, banner "Market closed. Prices are from 27 Oct 2026, 18:55:36 IST.", 0 "not connected"; core tests 18/18 on db_run_fresh; vitest 1203/1203 |
| F-18 | U-5, U-6, U-18 (walk 3, real app) | After hours the strike drawer shows "-" for every strike it does not already hold (LTP, OI, IV, delta) and the depth popup says "Depth not available / The live feed is not fresh." (18:56-19:01; GET leg-picker/depth -> NOT_AVAILABLE FEED_STALE) | functional (ADR-200 (1): the drawer uses the last price too) | drawer cells and the depth popup read live-only health; plus a first-read race: a newly subscribed contract has no snapshot for ~4 s after hours (measured: the same strikes request "unavailable" then priced 6 s later) | `708ea911` (drawer OI/IV/delta from the last close; depth popup `depth_after_close`, market_closed field; Execute depth unchanged) | PASS LIVE 19:10: drawer priced after 3.98 s, Greeks view, depth Open 189.95 / 5 levels; route tests 75/75 on db_run_fresh |
| F-19 | walk 5 (real app, 07:46-07:52 IST, before the open) | Every after-hours time label shows the morning's snapshot ARRIVAL time: banner "Market closed. Prices are from 28 Oct 2026, 07:46:17 IST", entries "Close, 28 Oct 2026, 07:47:44 IST", while the prices are 27 Oct's close (index at=07:46:28, health stale) | functional (ADR-200 (2), ADR-197) | kite_provider.py:176 stamps a tick without exchange_ts with received_at, so the "quote's own time" is itself a frame time; 2nd occurrence of the label-time class -> independent reviewer RCA before the fix (owner rule) | RCA running | owed |
| F-20 | walk 5 U-18 (07:52 IST) | Depth popup before the open: "Depth not available / The live feed is not fresh.", reply market_closed:false, FEED_STALE | functional (ADR-200 (2): never "not fresh" when closed) | leg_picker._held_after_close returns None when the held book is empty (pre-open book is empty), so depth_answer falls through to the in-hours FEED_STALE answer with market_closed defaulting to false | queued with F-19 | owed |
| F-10 | U-12 | Mixed expiry, At Expiry: the chart kept the previous condor curve, no reason (16:28, u12-chart-expiry.png) | functional | PayoffChart returned early on an empty point list before destroying the old chart | G-065 round 2 `0cc230e4`; live re-check 16:34 shows the ADR-143 line (f10-after.png) | PASS (closing prices) |

### Extra checks outside the U-list (closing prices, 2026-10-27 18:00-18:14 IST)
- SENSEX condor: 73200/73400 PE, 73800/74000 CE on 29 Oct, entries 277.80/352.55/301.00/224.40, net Rs 3,027 = 151.35 x 20, max loss 1,214.95, breakevens 73,248.65 / 73,951.35 (hand-checked); strike step +100; hover works. PASS.
- Undo after Clear all: 4 legs and the same max profit back. PASS. Save after an edit: PUT /strategies/39, same id, no name prompt (REQ-134 AC-2). PASS.
- History: lists "removed leg BUY 22550 PE 2026-11-03 x65; added leg BUY 22600 PE ..." with Restore. PASS (raw ISO date -> owner visual list).
- Start tracking (menu): scrolls to the tracking panel's own "Start tracking" button (two steps by design); not pressed. PASS.
- ?template=iron_condor (the Learn link path): load 200 + capture 200; after the close it lands on the expired expiry -> owner decision ADR-199 (roll to next), built as F-16.

- Test database finding (not this branch): ofo_test holds 1,085 catalogue_contracts rows, all first_seen 2026-10-21 21:29 IST (expiries 2026-10-08..19, the seed_test_catalogue fixture); tests_app/test_catalogue_picker_api.py asserts an empty table, so 5 of its tests fail locally. Not deleted (shared state, owner unknown); deferred issue at step 10; CI runs that file on a throwaway database.

### Walk 3 (REAL app, no launcher, after hours per ADR-200 (5)), 2026-10-27 18:55-19:02 IST
- U-1 NIFTY 22749.75; U-2 SENSEX 73598.67, default 29 Oct; U-3 condor / bull call / straddle and U-4 strangle 100 all priced, banner on every one, 0 "not connected", numbers identical to walks 1-2; U-9 strike step, U-10 untick, U-11 shift/width/hedge, U-13 multiplier, U-14 reset ("captured 18:57:32"), U-16 charges Rs 256.02; U-17 10/10 help; U-19 Estimated draws; U-20 hover 22,100 / 22,600 / 23,200 equal the table; U-21 table with both 0-P&L rows; U-22/U-23 totals; U-24 quantity 65; U-25/U-26 save 40, Save As pre-fill "GCBM walk3 copy" -> 41, rename; U-27 reopen same entries and max profit 4,581.68 with the banner; U-28 delete copy keeps original; U-29 clear, menu disabled; U-31 tabs; U-32 only the by-design tracking 404s and the favicon. PASS.
- FAIL: U-5/U-6 drawer cells "-" for unheld strikes and U-18 depth popup -> F-18. Not yet re-walked: U-5..U-8, U-12, U-18 after F-18.
- Noted, already tracked: the shape name and Hedge marks arrive 4-8 s after a load (G-019 edit speed, #560).

### Walk 4 (REAL app, no launcher, after hours per ADR-200 (5)), 2026-10-27 19:16-19:21 IST: CLEAN
- U-1 NIFTY 22749.75 | U-2 SENSEX 73598.67, default 29 Oct | U-3 condor 4,581.68 / 1,918.32, bull call 7,404.76 / 5,595.24, short straddle 25,522.97 / Unlimited | U-4 straddle, strangle 100 | U-5 drawer 3 Nov, 21 rows, no "Choose an expiry" | U-6 ATM 22750: 0.5295 185.00 1258140 13.65 / 17.98 992485 210.05 -0.4755 | U-7 4 picks priced | U-8 future 22807.90, mixed expiry "Not available", no 500 | U-9 strike +, Edit to SELL x2 (max loss 43,78,594.95 hand-checked), delete -> "Jade Lizard" | U-10 untick/tick | U-11 shift/width/hedge | U-12 leg 4 to 9 Nov: "Not available", "Width and Hedge need one expiry.", ADR-143 line, no 500 | U-13 x2/x1 | U-14 reset "captured 19:20:20" | U-15 net 6,366.75, breakevens 22,552.05 / 23,047.95, R/R 1.68, margin 62,558.60 | U-16 Rs 256.02 | U-17 10/10 | U-18 Open 134.00 ... 6 rows | U-19/U-20 hovers equal the table | U-21 both 0-P&L rows + CURRENT | U-22/U-23 totals | U-24 quantity 65 | U-25..U-28 save 42, Save As 43 ("GCBM walk4 copy"), rename, reopen same entries, delete copy | U-29 clear, menu disabled | U-30 red block (U-15 reading) | U-31 tabs | U-32 only the by-design tracking 404s (+ their console line).
- Zero functional FAILs: the walk condition of the stop condition is met (ADR-200 (5)).

### Walk 5 (REAL app, owner's fresh Kite login, BEFORE the open), 2026-10-28 07:47-07:52 IST
- Every functional step passes: U-1 NIFTY 22749.75 with the banner on the EMPTY page (round-1 fix live) | U-2 defaults SENSEX 29 Oct, NIFTY 3 Nov | U-3/U-4 all priced | U-5 drawer 3 Nov, 21 rows, drawer banner shown | U-6 ATM 0.5255 201.40 ... | U-7 picks priced | U-8 future (29 Dec, the 27 Oct monthly has expired) | U-9..U-16 as before (condor MP 4,661.67 on this morning's snapshot) | U-12 mixed expiry Not available, no 500 | U-17 10/10 | U-19..U-24 | U-25..U-29 (saved 44, copy 45) | U-31 | U-32 only the tracking 404s.
- FAIL: every time label (F-19) and the depth popup (F-20). U-27 shows "captured 07:51:23" on the reopened saved strategy: the PARKED item (needs a migration), as expected.

### Session break, 2026-10-28 08:20 IST (context full; continue in a fresh session)
- F-19/F-20 round 3 merged into build/gcbm-must-have (d06f4672): price_at = session close outside market hours
  (market_calendar.last_close / price_time), every closed-market label reads it; depth popup answers MARKET_CLOSED
  when closed. Builder: 12 red first; mutations caught.
- Orchestrator after the merge: domain suite (tests/test_*.py + errors + marketdata + outcome) 1938 passed / 3 skipped;
  db_run_fresh on 11 route files 1 failed / 261 passed. The failure: tests_app/test_market_closed_answers.py:84
  `assert _instant(chain["last_price_at"]) == frame_at` -> None: the Saturday case pinned the chain label to the FRAME
  time, which ADR-200 (2) forbids. Fix the assertion to the ADR-200 rule (session close, or None with no priced quote).
- NOT yet done after the merge: full vitest; builder leftovers (popup no-levels branch hides the day values; one F-20
  test does not reach the empty-book path - tighten; broker-status text "Prices are from 03:30:00 PM" has no date ->
  deferred issue 8); restart API + vite (kill the running 8765/5174 by PID first); re-walk the label surfaces + depth
  popup (expect "27 Oct 2026, 15:30 IST" and "Close, 27 Oct 2026, 15:30 IST"); after 09:15 the in-hours check (live
  prices, NO banner, captions "captured HH:MM:SS"); then step 9: ruff ratchet + coverage + openapi drift, local
  Playwright (copy of e2e_local2.sh: run inside db_run_fresh, loads the main .env keys except DATABASE/APP_ENV/LIVE_MARKET,
  plain API 8000 + replay API 8001 + previews 4173-4175, kill by PID), prepush.py with the servers STOPPED, ONE push,
  ONE PR (no closing keywords; Spec-deviation block; deferred issues 1-8 via gh_issue.py app ... --stage), CI,
  merge.py <pr> --reviewed-sha <sha>; then wt-rm.ps1 for the gcbm-* worktrees once merged on origin/main.

## Visual differences for the owner (not fixed here)

| U-step | Ours | Sensibull (screen) | Existing gap row |
|---|---|---|---|
| U-9 | B/S and CE/PE flip and lots only through Edit (pencil) | flips and lots box in the row (S-107) | G-015 |
| U-9 | "2 lot" | "2 lots" | none |
| U-7 | Drawer shows "0 selected" with 2 legs already in the strategy; existing legs not shown as picked | footer "2 legs selected" (S-032) | G-079 |
| U-5 | Escape did not close the drawer once (16:09); not reproduced 18:02 (closed on the first press) | - | none |
| U-8 | Futures tab: the "Add a leg by contract" block overlaps the forward list | only the futures list (S-034) | G-080 |
| U-12 | Edit leg: changing the expiry clears Type, so the strike list is empty until Type is chosen again | - | none |
| U-2 | With legs, the underlying select is replaced by plain text (no way to switch without Clear all); spec silent | switch asks first (S-107) | G-001 |
| U-3 | Bull Call Spread marks the SELL 22950 CE as Hedge (template data, REQ-076 AC-8) | - | owner question: which leg is protective |
| U-19 | Estimated Now view still labels the x axis "Index level at expiry" | - | none |
| U-21 | Payoff table: 100-point rows, one at-expiry column, no interval picker / target column / Show % | REQ-137 (S-017) | missing feature, not a broken one |
| U-22 | P&L table expiry raw "2026-11-03"; total "+0.0%" vs legs "0.00%" | "3 Nov" (S-014) | none |
| U-23 | IV as a raw fraction "0.176762" | "17.7" (S-015) | G-0xx IV format |
| U-25 | Saved list rows lack the first-leg summary and tracked state | REQ-134 AC-4, S-118 | missing piece |
| U-1 | /favicon.ico 404 | - | none |
| U-5 (after hours) | The drawer's prices fill ~4 s after the first open after hours (new contracts' snapshots arrive late); in hours < 1 s | prices at once | none |
| (extra) | History entries print the expiry raw ("2026-11-03") | - | none |
| U-3 | After a card click the builder shows "No legs yet" for 2-5 s (cards greyed, no loading text) while F-1 captures prices | legs appear at once (S-011) | none; time it live |
| after close | Ready-made, drawer and the ?template= link default to today's expiry after 15:30 on expiry day, so the legs cannot be priced (?template=iron_condor at 18:07: load 200, capture 200, 4 legs on 27 Oct, "not connected"); drawer prices "-" for strikes not held | unmeasured | OWNER QUESTION: should the default roll to the next expiry after the close on expiry day? spec silent (REQ-135 AC-2 only names "Today (0 days)") |

## Rules carried from the builder-phase contracts

- Every build brief: `Core:` / `Proof:`, `Spec basis:` with quotes, `Sensibull:` with screen numbers, `Copy from:`,
  `Budget: <N> min wall-clock, <M> tool calls`, `Report: evidence-table`, the C4 standing items a-d, and the coding-
  standards line ("no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted
  tests only; no regenerated files in the PR"). In place of Common rule 1: "do NOT run ci_local / prepush; run only the
  tests of the files you touch, plus every test file and e2e spec that shows a value you changed".
- At most 2 fix rounds per F-row; then park it (issue labelled `parked`, evidence, what is left). The contract then ends
  PARTIAL naming it. A parked F-row is never counted as passed.
- Market closed: steps 2-8 may build against the recorded replay, labelled as replay; the live walks are still owed
  and run first in the next market session. The contract does not close on replay walks alone.
- AMENDED 2026-10-27 ~18:17 IST by the owner (ADR-200 (5)): a walk on the REAL app outside market hours, priced from
  the last close and labelled "Market closed. Prices are from <time>." (F-17), counts as the live proof. A walk through
  the walkthrough launcher that pretends the market is open does NOT count (walks 1 and 2 used it).
- Never run the full pass while the app servers are up (3.8 GB free killed the app on 2026-10-27).

## Stop condition

Steps 0-10 done; the last user walk has zero functional FAILs on the live app in market hours; every F-row fixed or
parked; one push; CI green; merged with `merge.py`; handover on main. Otherwise PARTIAL with the owed items named.

## /goal prompt (owner pastes this in a fresh session)

```
/goal Run goal contract GC-BM: docs/process/goal-contract-GC-BM-2026-10-27.md on local branch build/gcbm-must-have
(worktree D:\Abhay\Ventures\OptionsForOptions2-gcbm; the file is NOT on main). Build the 5 must-have builder rows
(G-065, G-070, G-075, G-024, G-051), then test the live builder and strike drawer as a user with the full U-list,
fix every functional issue found (compare with Sensibull), and repeat the walk until one full pass is clean. Visual-only
differences go to the owner list, not fixed. No CI of any kind (no push, PR, ci_local, prepush, land) until step 9;
builders run only targeted tests. Then one full local pass, one push, one PR, one CI run, merge, handover. Live walks
need market hours (09:15-15:30 IST) and my cached Kite token; never press an order button.
```

## Handover, 2026-10-28 06:40 IST

- DONE: steps 0-8. The 5 must-have rows (G-065, G-070, G-075, G-024, G-051) and F-1, F-8, F-10..F-18 fixed with failing
  tests first; owner decisions ADR-199 (expiry default rolls after the close on an expiry day) and ADR-200 (builds
  ADR-197 now; "last close" defined; real-app closing-price walks prove this contract). Walk 4 on the real app after
  hours: CLEAN, U-1..U-32. Review round 1 + round 2: Tier A (Opus) PASS, Tier B (Sonnet) PASS. Local: full vitest
  1217/1217, ruff ratchet OK, coverage OK, openapi no drift, after-hours / drawer / execute / catalogue route tests green
  on db_run_fresh (throwaway databases; ofo_test is dirty, see below). Gap list re-verdicts written (G-070, G-075
  matches; G-024, G-051, G-065 differs with reasons) and the counts recounted.
- PENDING: walk 5 on the FINAL code (the review fixes changed the labels and the close caption after walk 4) and a
  short in-hours check after 09:15 (live prices, no banner); then step 9: Playwright for the changed pages, prepush with
  the servers stopped, ONE push, ONE PR, CI, merge.py; deferred issues filed (list below).
- BLOCKED: the Kite access token expired at 06:00 IST (Kite's daily expiry); the API logs "no active Kite session".
  Needs one owner login in a PRIVATE window: http://127.0.0.1:8765/broker/zerodha/login (the API runs on 8765).
- PARKED: the ADR-197 close label on a SAVED strategy reopened later (needs a migration: 0011 / 0024 allow only fixed
  leg keys; migrations need draft-PR CI under ADR-191 (2)); after two fix rounds it ships listed. The screen then reads
  "captured <time>" instead of "Close, <date>, <time> IST" - the numbers are right.
- Local Playwright (2026-10-28 ~07:00 IST, db_run_fresh throwaway DB, plain API 8000 + replay API 8001, previews 4173-4175,
  the CI env keys loaded from the main .env, never printed): builder specs 78 passed / 8 skipped / 2 failed -> the 2 were
  one stale assertion (leg-picker.spec.ts:57 pinned raw "2026-10-13", REQ-148 AC-2 makes it "13 Oct"), fixed e7d82f4d,
  re-run 8/8. Whole suite: 264 passed / 20 skipped / 6 failed = health.spec (database: ok), strategy-table.spec:85
  (max profit 4754.75 vs 4539.65, i.e. no charges) and leg-picker.spec:68 under full-suite load; the first two fail
  IDENTICALLY on main (f27e7b54) in the same local set-up (no pinned catalogue date / seeded data as CI has), and
  leg-picker passed alone. Branch-attributable e2e failures: 0. CI decides the rest.
- NEXT: after this PR merges, GC-B2 (docs/process/goal-contracts-builder-phase-2026-10-27.md), owner sets it as /goal.

Deferred issues to file with the PR (gh_issue.py app ... --stage):
1. Close label on reopened saved strategies (the PARKED item above; migration + save/load paths).
2. Option Chain still defaults to its first listed expiry after the close (ADR-199 consequence; chain phase).
3. ofo_test on the VPS holds old rows (catalogue 1,085 from 2026-10-21, broker_sessions 507, audit 365, strategies 40):
   decide wipe or retire; DB tests now use db_run_fresh.py.
4. ADR-008 scan MINORs left after round 2: two apostrophes on one template line hide money maths between them; a unary
   minus (`-p.pnl`) passes.
5. Market calendar holds 2026 only: from 2027-01-01 the closed-market rule would misjudge trading days.
6. leg-edit echoes a client-sent close_at for legs it does not re-capture (caption only).
7. After hours the drawer's first open fills prices ~4 s late (new contracts' snapshots arrive late).
8. Broker-status text "Prices are from 03:30:00 PM" carries no date (every other closed label reads "27 Oct 2026, 15:30 IST").
