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
| 8 | user walk 2..n | Repeat the FULL U-list after the fixes. A new functional failure becomes an F-row and goes back to step 7. Stop when one full pass has zero functional FAILs | C | A clean walk table, timestamped, with screenshots | Walk 2 (closing prices, about 17:00-17:08): U-1..U-32 all pass except U-5/U-7 (F-12, fixed 17:10); not clean, so walk 3 is owed and must be LIVE (market hours) |
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
| F-17 | (owner, ADR-200) | Outside market hours the real app shows no prices at all (index "unavailable", legs "Draft - Live data not connected", no summary/chart; 15:58 IST) while REQ-105 AC-4 / REQ-114 AC-7 say the last close is shown labelled | functional (approved requirement not met) | to be measured: the closed-market state makes every quote unhealthy for pricing | building | owed: core proof on the real app, no launcher |
| F-10 | U-12 | Mixed expiry, At Expiry: the chart kept the previous condor curve, no reason (16:28, u12-chart-expiry.png) | functional | PayoffChart returned early on an empty point list before destroying the old chart | G-065 round 2 `0cc230e4`; live re-check 16:34 shows the ADR-143 line (f10-after.png) | PASS (closing prices) |

### Extra checks outside the U-list (closing prices, 2026-10-27 18:00-18:14 IST)
- SENSEX condor: 73200/73400 PE, 73800/74000 CE on 29 Oct, entries 277.80/352.55/301.00/224.40, net Rs 3,027 = 151.35 x 20, max loss 1,214.95, breakevens 73,248.65 / 73,951.35 (hand-checked); strike step +100; hover works. PASS.
- Undo after Clear all: 4 legs and the same max profit back. PASS. Save after an edit: PUT /strategies/39, same id, no name prompt (REQ-134 AC-2). PASS.
- History: lists "removed leg BUY 22550 PE 2026-11-03 x65; added leg BUY 22600 PE ..." with Restore. PASS (raw ISO date -> owner visual list).
- Start tracking (menu): scrolls to the tracking panel's own "Start tracking" button (two steps by design); not pressed. PASS.
- ?template=iron_condor (the Learn link path): load 200 + capture 200; after the close it lands on the expired expiry -> owner decision ADR-199 (roll to next), built as F-16.

- Test database finding (not this branch): ofo_test holds 1,085 catalogue_contracts rows, all first_seen 2026-10-21 21:29 IST (expiries 2026-10-08..19, the seed_test_catalogue fixture); tests_app/test_catalogue_picker_api.py asserts an empty table, so 5 of its tests fail locally. Not deleted (shared state, owner unknown); deferred issue at step 10; CI runs that file on a throwaway database.

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

## Handover at 17:10 IST, 2026-10-27 (market closed; next session or this one at 09:15 on 2026-10-28)

- DONE (closing prices, LIVE_MARKET=1 + the walkthrough launcher, ofo_dev): steps 0, 2-6 built and checked; F-1, F-8, F-10,
  F-11, F-12 fixed; walk 1 and walk 2 recorded above. Local branch head is in `git log -1`; full vitest 1181/1181.
- PENDING, in order: (1) 09:15 LIVE walk 3, full U-list (dev server: `npx vite --port 5174` in this worktree's frontend
  with OFO_API_TARGET=http://127.0.0.1:8765; API: `LIVE_MARKET=1 APP_ENV=development python <main>/scripts/orchestrator/dev_run.py . python -m uvicorn ...`
  WITHOUT the closing-price launcher once the market is open); include F-2 (blank leg rows, seen once) and F-3 (drawer
  strikes ~30 s, 10+ repeated reads) live, and the after-close items in the owner list; (2) any new functional FAIL -> F-row
  -> step 7 -> walk again; (3) step 9 final gate with servers STOPPED, one combined review (Opus for G-065, G-051, F-8;
  Sonnet for the rest), one push, one PR, CI, merge.py; (4) step 10 handover docs in the same PR.
- Builder worktrees -gcbm-g065/-g070/-g024/-g051/-f1/-f8 stay until main has the merge (wt-rm.ps1 needs the sha on origin/main).
- Spec note for the owner list: scenario-calculations section 3 says futures add 0 to net premium; REQ-081 AC-1 says a
  futures leg makes net premium "-" (the screen follows REQ-081). Futures charges are not priced (charges/round_trip.py:
  options-only rate table), labelled on screen.
