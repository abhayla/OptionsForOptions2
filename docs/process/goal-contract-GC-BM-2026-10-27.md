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
| 0 | setup | `npm ci` in the worktree's `frontend/` (the junction helper found no modules on 2026-10-27; use a real install, never a junction). Merge local branch `build/c3-small-f2-f5` (4 commits, #537 F2 + ADR-192 Save As pre-fill, not on main; it touches `SaveDraftBar.vue` / `saveDraft.js`, the same files as step 5) and run its tests: `save-draft.test.js`, `draft-link.test.js`, `tests/execution/test_margin_gate.py`, `tests/execution/test_safety_checks.py` | C | Tests green, merge commit recorded here | Not started |
| 1 | core proof | User walk 1 (the U-list below) on the live app, before any change. Each U-step gets pass / FAIL with what was seen and a screenshot name. FAILs that are functional become rows F-1, F-2 ... in the "Found in the walk" table | C | The walk table filled in | Not started |
| 2 | G-065 (#586) | Moving one leg to another expiry answers instead of a 500: the summary and chart stay, the leg shows "9 Nov (13 days)" not "2026-11-09", Width / Hedge disabled with a reason, label and curve per ADR-143 (Sensibull S-104) | A | Live 4-leg NIFTY condor, leg 4 moved to the next expiry: numbers and chart shown, no ERR- code | Not started |
| 3 | G-070 | The drawer opens on the nearest expiry with its strikes listed (S-032) | B | Open Add/Edit: expiry chosen, ATM rows visible, no "Choose an expiry" text | Not started |
| 4 | G-075 | Every drawer value sits in its own column at 520 px: no run-together cells, Put LTP not cut (S-032) | B | First 3 strike rows read cell by cell, one value per cell; screenshot next to S-032 | Not started |
| 5 | G-024 | The "..." menu offers Save, Save As and Rename and each works (REQ-134, ADR-192; Share stays out, ADR-196 (4)); on an unsaved strategy, only the items that apply, never an empty menu (S-023, S-115) | B | Save As on a 4-leg strategy makes a named copy, Rename changes the name, both read back from the Saved tab | Not started |
| 6 | G-051 | Hovering the payoff chart shows the price, its % from spot and the P&L at that price (REQ-083; S-122) | A (P&L number from the one engine, ADR-008) | Hover at 3 x positions; each tooltip's P&L equals the payoff-table value at that level | Not started |
| 7 | F-rows | Fix every functional failure from walk 1, one class at a time (RCA, failing test first, class fix) | per row | Each F-row's U-step passes on the live screen | Not started |
| 8 | user walk 2..n | Repeat the FULL U-list after the fixes. A new functional failure becomes an F-row and goes back to step 7. Stop when one full pass has zero functional FAILs | C | A clean walk table, timestamped, with screenshots | Not started |
| 9 | final gate | `python scripts/generate_openapi.py` drift check; Playwright for the changed pages (`npx playwright test <specs>`, servers per runbook, stopped after); `python scripts/ruff_ratchet.py`; `python scripts/orchestrator/coverage.py . --check`; then `python scripts/orchestrator/prepush.py` with app servers stopped. One combined review: fresh Opus for steps 2 and 6 and any Tier A F-row, Sonnet for the rest, at most 2 rounds. Then ONE push, ONE PR (Spec-deviation block, no closing keywords), CI, `merge.py <pr> --reviewed-sha <sha>` | A/B | Every command's tail line; CI green on the PR sha; main has the files | Not started |
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

## Visual differences for the owner (not fixed here)

| U-step | Ours | Sensibull (screen) | Existing gap row |
|---|---|---|---|

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
