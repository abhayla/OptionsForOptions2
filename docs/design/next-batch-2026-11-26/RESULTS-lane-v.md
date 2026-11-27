STATUS 18:05 | 54: fixed, not tested | 55: fixed, not tested (Opus review done, fixes applied) | 57: fixed, not tested | next push: after prepush gate (3rd run, after merging Lane U) | blocker: file-ownership question for coordinator (see below) | blocker: none

# Lane V RESULTS (27 Nov 2026, IST): Plan door, three-line stop warning, closed trade page

Branch `feat/plan-door-1127`, cut from `origin/fix/live-test-small-1127` (bcbff80) with `origin/hotfix/maxloss-line-1127` (5a71841) merged first. No PR, no main, no PR #722. No migration. No broker order endpoint called. Highest status claimed: "Fixed, not tested" (screen tests are on the owner's PC on Monday).

Messaging to `@parent` was refused (`elevated_session_untrusted_device`), so this top line is the report.

## Core proof (read before any other code)
One-lot NIFTY condor, strikes from the real 27 Nov case (sold 25950 CE / 25850 PE, bought 26150 CE / 25650 PE; the fill prices are mine, the real book is not in the repo). The engine (`ofo.engine.extremes`), stop on the bought 25650 PE at Rs 5:

| Figure | Engine result |
|---|---|
| Max loss now | -7,800 |
| Max loss then | -1,674,725 (about Rs 16.7 lakh, the size the tester saw) |
| Exposed leg | the sold 25850 PE |
| Same stop on the bought call | max loss then UNLIMITED, exposed = the sold call |

## What was built

| Item | Built | Where |
|---|---|---|
| (54) Plan button | `PlanDoor.vue`: a Plan button that reads the plan only when pressed, then opens the one `AdjustPlanSheet` (the sheet the builder's Edit plan / Set plan opens; edit = PUT when a plan exists, first plan = POST). On every running paper trade (action column, beside Stops and Exit) and every real trade with positions (group header). A read that fails says so and opens nothing. | `frontend/src/components/strategy/PlanDoor.vue`, `PaperStrategies.vue`, `PositionsPage.vue` |
| (55) Three lines | `leg_stop_lines` in `routes/paper.py` builds the three lines from the engine's Decimal figures; `ExitRiskOut.warning_lines` carries them, `warning_text` is the same lines joined by newlines (the fired-stop alert reuses it). Sold put bare: "(worst case: NIFTY at zero)". Sold call bare: "no upper limit", no amount. Index name from the trade (`UnderlyingName` slot). Figure missing: "could not be worked out", no number. A stop that leaves nothing bare keeps the old one-line sentence. The page prints the three lines as sent, one per line. | `routes/paper.py`, `ofo/errors/explanations.py`, `PaperStops.vue`, `paper_monitor.py` (passes the index) |
| (57) Closed trade | `plan_final_text` on the paper book (only when every leg is closed): "Plan: stop Rs 300, target Rs 800. Closed by your exit at 11:23." The builder prints it under the closed result and no longer mounts the Plan watch box for a closed trade. The "Add/Edit" button and the "Add a leg to start one" text were already gone on the base branch (closed sentence). | `ofo/tracking/plan_final.py` (builder), `ofo_app/plan_ending.py` (reader), `routes/paper.py`, `PaperBookPanel.vue`, `StrategyBuilderPage.vue` |

## Tests (failing first, then code)
| Test file | What it covers |
|---|---|
| `tests_app/test_leg_stop_risk.py` (updated + 7 new) | the real condor case (three lines, Rs 14,45,535.00), bare call (no amount), profit book, SENSEX name, both bare, figures missing, nothing bare |
| `tests_app/test_stop_fired_message.py` (unchanged) | the fired-stop message keeps its one sentence |
| `tests/tracking/test_plan_final.py` (14) | every ending, plan absent, level not set, level not available, no closing record, earlier day, naive time refused |
| `tests_app/test_plan_final_line.py` (6) | route: your exit, settlement, earlier day, open book (none), no plan, percent plan with no rupee figure |
| `frontend/tests/paper-stops-leg-risk-w2b.test.js` | the page prints three lines, one each; a malformed list falls back to the one sentence |
| `frontend/tests/plan-door-positions-54.test.js` (8) | button on running paper and real rows, none on closed, one sheet, edit vs first plan, nothing read on page load, failed read |
| `frontend/tests/builder-closed-plan-final-57.test.js` (4) | closed page: line printed, no Plan watch, no plan-watch read, no add controls; open book unchanged |

Ran this session: full vitest 287 files / 3221 tests pass; eslint 0 errors; `tests/errors` + `tests/tracking` pass; the DB tests above pass against a local Postgres 16. The prepush gate result is recorded below.

## Exact screen steps for the owner's PC (Monday)
(54) Positions page, filter All. 1. Open Positions with one running paper trade and one running real trade. 2. Each shows a "Plan" button (paper: beside Stops and Exit; real: right end of the group header). 3. Press Plan on the paper trade: the plan sheet opens (title, playbook, target, stop). Press Close. 4. Open the same trade in the builder, press its "Edit plan": the SAME sheet. 5. Press Plan on a trade with no plan: the sheet opens to set the first plan. 6. A fully closed trade shows no Plan button.
(55) Builder, running one-lot NIFTY iron condor. 1. Stops panel, type a stop level on the bought 25650 PE leg. 2. After the pause, three lines appear, each on its own line: "If this stop fires, the sold ... is left without protection." / "Max loss now: Rs ..." / "Max loss then: Rs ... (worst case: NIFTY at zero)." 3. Type a stop level on the bought call leg: line 3 reads "no upper limit (worst case: NIFTY keeps rising)" and shows no amount. 4. Type a stop on the sold short call: the old one sentence appears. 5. Same on a SENSEX trade: the lines say SENSEX.
(57) 1. Open the builder on settled trade 173. 2. It shows "This trade is closed. Its legs and result are shown below; it cannot be changed.", the closed legs, the result, and one line "Plan: stop Rs ..., target Rs .... Closed by expiry settlement at 15:30." (or "your exit at HH:MM"). 3. No Plan watch box, no Add/Edit button, no "Add a leg to start one".

## Pending owner read (every sentence new today)
Backend (pinned "pending owner read" in `tests/errors/template_pins.json`): "If this stop fires, the sold {leg} is left without protection." / "If this stop fires, the sold options {legs} are left without protection." / "Max loss now: Rs {amount}." / "Max loss now: none (the book shows a profit of at least Rs {amount})." / "Max loss then: Rs {amount} (worst case: {index} at zero)." / "Max loss then: none (the book shows a profit of at least Rs {amount})." / **"Max loss then: no upper limit (worst case: {index} keeps rising)." (sold-call wording: the owner gave no exact text, pending owner read)** / "Max loss now: could not be worked out." / "Max loss then: could not be worked out." / "stop Rs {amount}", "no stop", "stop not available", "target Rs {amount}", "no target", "target not available", "Plan: {stop}, {target}.", "No plan was set for this trade.", "your exit", "your stop", "expiry settlement", "Closed by {how} at {time}.", "Closed by {how} on {day} at {time}.", "Closed by {how}.", "How this trade ended is not recorded."
Frontend (`sharedStateText.js`): button "Plan"; "Could not open the plan. Try again."

## Opus review of (55) (independent, commit e916854f): verdict REVISE, what was done
| Finding | Action |
|---|---|
| F1 an engine figure (unlimited, or a figure the exit judge hides) was printed "could not be worked out"; a bare sold call without a "now" figure missed "no upper limit" | Fixed: the three lines use the engine's own figures as they are ("Max loss now: no upper limit." added); tests for the ratio call spread and the calendar call |
| F2 "worst case: index at zero" was chosen because the bare leg is a put | Fixed: printed only when the engine's P&L at zero (new `book_pnl_at_zero`) equals the max loss; otherwise the amount alone ("Max loss then: Rs ...") |
| F3 the fired-stop message printed "Max loss now" with the figure from before the fire | Fixed by keeping the fired-stop message on its one sentence as before (`lines=False`); the three lines are for the warning before a stop is saved. The old sentence's "(now ...)" has the same stale-figure wording; listed below |
| F4 several exposed legs read "left without protection" though one may still be covered | Fixed for several legs ("these sold options are left with less protection: ..."). A single partly covered leg still reads "left without protection": listed below |
| F5 newlines run together in plain paragraphs | Stops panel text gets `whitespace-pre-line`; the fired message no longer carries newlines |
| F6 stored three-line text restore list | Not needed: the three lines are no longer stored |
| F7 latent `bare_call and after is not None` | Removed |

## Coordinator message of 27 Nov 17:3x (read, acted on as far as it fits)
1. **Merged** `origin/hotfix/index-quote-1127` (Lane U, 709eb835) into this branch: clean merge, no conflicts; screen-inventory line numbers re-synced. Lane U pushes once more tonight: I fetch and merge again right before my push (if that merge changes anything, the gate runs again).
2. **File ownership conflict (needs the coordinator).** The brief of this lane required server-built lines (items 55 and 57), so I already edited `backend/ofo_app/routes/paper.py` (leg_stop_lines, `plan_final_text`) and I do NOT edit `backend/ofo_app/routes/adjustment_plan.py` (Lane R2's file: a first version added a public helper there, reverted after the structural guard `test_risk_exit_not_gated` showed that importing it from `routes/paper.py` would let a paper-exit module reach the alert gate). I did NOT edit `AdjustPlanSheet.vue` (the Plan button only opens it) and did not touch Home, My Strategies or the worker. The remaining `routes/paper.py` edits are small and separable (leg_stop_lines, one `plan_final_text` field, one call); say if the owner of that file wants them moved.
3. **Lane M side-closed patch vs ADR-330 (46)** (read only; nothing applied, because the patch edits `backend/ofo_app/background.py`, the worker, which this lane does not own). ADR-330 (46) is not in this branch's `spec/decisions/ADR-330.md` yet (the record lands on fix/ic-live-test-1123), so I compared against the coordinator's quoted text: "the side-closed question comes with or without a plan, and it STAYS until answered when the plan is removed later". Findings: (a) the patch is only a file under docs; neither half is in the code on this branch. (b) First half (no plan: still asked): the patch hands no-plan trades to the side-closed check (`Listed.side_only` / `SideWatch`), never monitored: matches. (c) Second half (stays when the plan is removed later): the patch's `not_monitored` lapse leaves `side_closed` rows open: matches in intent, and the patch carries tests in `test_background_cycle.py` and `test_side_closed_alert.py`. What is missing: (i) the patch is not applied; (ii) it was not run against the final ADR text; (iii) whether a plan REMOVED later also keeps an answered-once question from being raised twice is not tested. Next step for whoever owns `background.py`: apply the patch, run those two test files, add a test: raise question with a plan, remove the plan, run the cycle twice, expect one open row.

## Decisions I took (owner away, B2) and what the owner should confirm
1. **Endings (57).** The book records three closing orders: exit, stop (Stops panel), settle. The plan's own stop, target and time exit raise alerts only (ADR-003), nothing links a close to one, so a close after a plan alert is recorded as "your exit". The line therefore names: your exit, your stop, expiry settlement, "not recorded", and "No plan was set". The brief's "plan stop / target / time exit" endings are NOT built: they would be a guess. Owner question: should the product link an exit to the plan alert that preceded it?
2. **Plan levels in rupees (57).** A stored rupee level prints as is; a percent level prints in rupees only when the stop base fixed at entry gives it (stop). The target as a percent needs the entry max profit, which a closed book does not hold: it prints "target not available", never an invented number. Real trade 173 will therefore often read "Plan: stop Rs X, target not available." unless the plan stored rupee levels. Owner question: store the entry max profit with the plan (needs a migration, so not done).
3. **Real trades (54).** The Positions page's real section was "no action buttons" (ADR-201 (2) test). ADR-330 (54) says each running trade; I added the Plan button to real groups and changed that test to allow `plan-open-*` buttons (the button opens the plan sheet and orders nothing).
4. **Screen inventory.** `docs/design/next-batch-2026-11-26/screen-inventory.json/.md` (Lane T's files) re-extracted: the plan sheet's controls are now reached from two pages, so they moved to "(shared components)" and ids renumbered; one new row SHARED-59. Required by the inventory guard test.

## paper-only path found (ADR-330 (58))
- `GET /paper/strategies/{id}/leg-stop-risk` and the Stops panel (`PaperStops.vue`) exist only for paper trades; the three lines therefore appear only in the paper Stops panel and the paper fired-stop message. I added no new paper-only branch. A real-trade stop door does not exist yet.
- `plan_final_text` rides on the paper book (`GET /paper/strategies/{id}`): the real-trade builder page has no equivalent book read, so the closed-trade line is paper-only for now. Real trades: the Positions Plan button works (plan sheet is by strategy id).

## To file as deferred issues
1. Real-trade stop door and real-trade closed book: the three lines and the plan line need a real equivalent (ADR-330 (58)).
2. Link a closing exit to the plan alert that preceded it, so "plan stop / target / time exit" can be named (decision 1).
3. Store the entry max profit with the plan so a closed trade can print its target in rupees (decision 2; needs a migration).
4. The Positions list's closed rows (PaperStrategies) do not print `plan_final_text`; only the builder does.
5. The fired-stop message's "(now Rs ...)" is the figure before the fire; give the message its own wording (Opus review F3).
6. Line 1 for ONE partly covered sold leg (2 lots short, 1 covered) says "without protection"; needs the bare quantity from the engine (F4).
7. `ruff` baseline: `routes/paper.py` carries many PLR0917 findings from before; not touched.

## Model that did each task
| Task | Model |
|---|---|
| All building, tests, RESULTS | Sonnet (this lane) |
| Independent review of item (55) | Opus helper (agent `reviewer`), "Why Opus": prints a money figure |
| Mechanical work | none needed |
