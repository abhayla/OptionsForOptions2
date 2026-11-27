STATUS 19:30 | queue A pushed (68ebb119, gate TOTAL PASS); queue B: items 8, 10, 12 Fixed/tested, not on PC; 9 and 11 moved to Lane L; Queue C removed | push B after its gate | blocker: none (send_message refused: session untrusted)

# Lane O results (branch fix/alert-screens-1127, cut from bcbff80)

Highest status used: "Fixed, not tested". Nothing is approved until it passes on the owner's PC.
Tests ran locally on a throw-away PostgreSQL 16 in the container (not the owner's tunnel).

## Queue A

| # | Item | State | Test (first failing, now passing) |
|---|------|-------|------------------------------------|
| 1 | T2-19 Reset markers | Built and tested, then REMOVED from this branch: files belong to Lane R2 (coordinator message 27 Nov). Patch: `lane-o-item1-for-lane-r2.patch` (tests included) | tests_app/test_adjustment_plan.py::test_reset_to_playbook_...; frontend/tests/plan-reset-p8.test.js |
| 2 | Alert row reason = trade name only | Fixed, not tested | tests_app/test_alert_routes.py::test_an_alert_with_no_worded_condition_shows_its_rule_not_the_trade_name |
| 3 | History error over a loaded list | Fixed (placement), cause of the failing request not proven | frontend/tests/alerts-history-d22.test.js (item 3) |
| 4 | Compare approaches "Now" label | PARKED | see below |
| 5 | Stop sentence date style | Fixed, not tested | tests_app/test_plan_watch.py::test_planned_condor_lines |
| 6 | Armed stop sentence | Fixed, not tested | same test, plus the paused test |
| 7 | Draft shows "strategy was not found" in Plan watch | Fixed, not tested | tests_app/test_plan_watch.py::test_a_just_saved_draft_reads_as_no_plan_never_not_found |

### Item 1 for lane R2 (apply `lane-o-item1-for-lane-r2.patch` with `git am`)
Before code: the real reset route answered no `put_back` field and the reset reply always had empty
`changed` / `switched_off` (a reset puts every condition back, so the old marker lines were empty by design, hence "not shown").
Fix: the reset reply now names what the plan differed in just before the reset (`put_back`, `put_back_off`), and the sheet prints it
with server-sent labels. The patch touches `AdjustPlanSheet.vue` (Reset marker block only), `adjustment_plan.py` (reset route and `_sheet`), `adjustPlan.js`, three label texts in `explanations.py` and two tests (7 vitest, 22 plan route tests passed). After applying, the template pins need three new entries (see `tests/errors/test_template_pins.py`).

### Screen steps (market CLOSED is fine)
1. (after Lane R2 applies the patch) T2-19: open a trade with a plan, Customise triggers, switch off T-05 and change another condition, save. Open the plan sheet, press "Reset to playbook", confirm. Expected under the button:
   "Put back to the playbook's values: triggers.T-02" and "Switched on again: triggers.T-05". If nothing differed: "Nothing differed from the playbook, so nothing was put back." The typed levels stay.
2. Alert rows: Alerts > Active, a plan stop / target / time-exit alert whose row used to show only the trade name. Expected reason line, for example "Plan loss stop: 15.5750 (rule 15.4000)"; with no figures: "Plan profit target". The title still reads "<name> (#id, expiry)".
3. Alerts > History: headings "Answered alerts" and "Stops and expiry settlements". If one read fails, its error line sits under its own heading and does not sit above the other list. If answered is empty but records exist: "No answered alerts yet."
5. and 6. Builder or Positions with a saved trade that has an armed leg stop: Plan watch, "Armed in the Stops panel". Expected "Leg stop on NIFTY 3 Nov 23450 CE: fires when the price rises above 90.00; price now 40.15" (date as "3 Nov", never 2026-11-03). Market closed: no "price now" part.
7. Save a draft in the builder (do not add to paper): Plan watch shows "No plan: nothing is watched for this strategy", not "This strategy was not found".

### pending owner read (old text -> new text)
- NEW "Put back to the playbook's values:", "Switched on again:", "Nothing differed from the playbook, so nothing was put back." (plan sheet labels)
- NEW alert rule line "<Plan loss stop | Plan profit target | Plan rupee stop | Plan rupee target | Plan time exit | Adjustment rule T-xx>: <value> (rule <threshold>)" ; replaces the trade name shown as the reason.
- NEW History headings "Answered alerts", "Stops and expiry settlements", line "No answered alerts yet."
- "Leg stop on X: price above L" -> "Leg stop on X: fires when the price rises above L" ; with a live price add "; price now P". Below: "falls below".
- Date in that sentence: "2026-12-01" -> "1 Dec" through the app's one formatter `display_contract`.
(Wording of item 6 is pending the owner's read, as briefed.)

### Item 4 parked (T2-12 "Now" label on the Compare approaches row)
Evidence: the opportunities list (`AdjustmentOpportunitiesPage.vue`) prints the stored record's condition with fired time only; there is no live value or as-of time in `GET /adjustment-opportunities` (the "Now ... (as of)" text exists only on the tracking panel's check reply, `live_value` / `live_as_of_text` in `adjustment_check.py`). A "Now" there needs a live check per strategy, or the worker (Lane J) storing the last reading with its time. Not guessed. Decision needed from owner / Lane J: which source is "Now".

### Item 6 direction check (coordinator point 2)
The stop is on the side the user chose and the worker honours it: `ofo/tracking/stops.py::crossed` fires an "above" leg stop when the live price is at or beyond the level on that side, so an "above" stop at 135.00 with a price of 113.10 is simply not yet crossed. The server does not tie the side to the leg (no check that a sold leg gets "above", a bought leg "below"); that is a product choice, not a stop defect, so no P0. For a bought leg an "above" stop is a profit exit; the new sentence says "fires when the price rises above 135.00; price now 113.10" so the side cannot be misread. Open question for the owner [guess]: should the Stops panel warn when a sold leg gets a "below" stop or a bought leg an "above" stop?

### 2028 date in the leg-stop warning (coordinator point 3, UX-07): not reproducible
Search: "2028" in backend/ofo, backend/ofo_app and frontend/src (only the U+2028 control-character patterns match; no literal date). The warning's contract name is built in `routes/paper.py::names_and_terms` from the STORED contract of the `contract_id` the page sends (`describe_contract`, the ISO date of that stored row), so a 2028 date means that id belongs to a Dec 2028 catalogue row, not a formatting slip. `tests_app/test_leg_stop_risk.py` asks with the strategy's own contract ids and passes. Likely cause [guess]: the page sent the id of another contract with the same strike. For lane V / K: log the contract_id on a warning and compare with the leg row. For lane K (`routes/paper.py`, not mine): `names_and_terms` should use `display_contract` ("1 Dec") instead of `describe_contract` (ISO), the same fix as item 5.

### Item 3 note
I could not tell which request failed on the owner's PC. Likely cause [guess]: `/alerts/answered` takes longer than the browser's 10 s limit because `alert_title.labels` reads the nearest expiry once per distinct trade. List for Lane J / deferred issue below.

### paper-only path found
None met in the files I changed.

## For lane R2 / K / L / V (page changes I may not make)
- For lane R2: item 1 patch above.
- For lane K: `routes/paper.py::names_and_terms` date style (see above).
- For lane L: item 9 (UX-05, UX-06) My Strategies after Undo: show a loading line instead of "No saved strategy matches" while the row returns, and grey "Show strategies" until it works; item 11 (UX-32) dropped (Lane L).

## Queue B

| # | Item | State |
|---|------|-------|
| 8 | UX-02 label the Stop price box and direction word | Fixed, not tested on PC. frontend/tests/paper-stops.test.js (UX-02) |
| 9 | UX-05, UX-06 My Strategies loading line | Moved to "For lane L" (their file) |
| 10 | UX-16, UX-24 Change expiry messages | Fixed (reason and captured price, server sentence); "keep a typed price" NOT done, see below. tests_app/test_leg_edit_route.py::test_ux16_ux24..., frontend/tests/leg-edit.test.js |
| 11 | UX-32 cards old after change elsewhere | Dropped (Lane L) |
| 12 | UX-27, UX-26 clicks | Click tests pass: "test-tool click, no defect" for the menu (6 sections, every item, frontend/tests/nav-every-item-ux26.test.js). "Pick from Option Chain": the click works (leg-picker test) but it only switches the columns back to LTP; with LTP already shown it does nothing visible, because the footer link exists only on the Strikes tab. That looks like "did not open". Owner decision: what should it open? Nothing changed. |

Queue C: removed from this lane by the coordinator.

### Screen steps, queue B (market CLOSED is fine)
8. Positions or builder, a saved trade, Stops panel, "Stop on a leg": each row now reads "Stop when the price goes [Above/Below]" and "Stop price [box]" (visible words, not only a hint).
10. Builder with a leg whose price you TYPED, then press Shift, Width, Hedge, a strike step or change the expiry so that leg moves. Expected under the leg list: "Your price for leg 1 was replaced by the captured price 12.30, because Shift moved the leg to another contract." (Hedge / Width likewise; expiry: "because you changed the expiry"; a strike step: "because you moved the strike"). If the new contract has no live price: "Your price for leg 1 was removed, because Shift moved the leg to another contract and the new contract has no live price right now." The captured price is printed, never the strike.
12. Click each top-menu item: each opens its page (test shows they do). In the picker, "Pick from Option Chain" with OI or Greeks shown switches back to LTP.

### pending owner read, queue B (new text)
- "Stop when the price goes", "Stop price" (Stops panel labels).
- "Your price for leg N was replaced by the captured price P, because <you changed the expiry | Shift/Width/Hedge moved the leg to another contract | you moved the strike>."
- "Your price for leg N was removed, because <reason> and the new contract has no live price right now."
- OLD: "Your price for leg N was replaced by the captured price of <strike> <CE|PE>." (printed the strike where the price belongs).

### Item 10, not done: "keep a typed price"
REQ-078 AC-8 says a typed price is replaced when its leg moves to another contract; keeping it would price the new contract at the old contract's price. Not changed: owner decision needed (keep the typed price, or replace with the said reason, as now).

### Edited outside the plain list, for awareness
`LegList.vue` (prints the server sentence instead of building one), `legEdit.js`, `routes/leg_edit.py` (new field `replaced_note`), `docs/api/openapi.json` and `tests_app/reply_inventory.py` (regenerated, one reviewer note written), fixture `frontend/tests/fixtures/leg-edit-controls.json` (one hand-added `replaced_note` on the recorded replaced leg).

## To file as deferred issues
- History `/alerts/answered`: per-trade expiry read may exceed 10 s with many trades (measure).
- Item 4: source of the "Now" value in the opportunities list (needs Lane J).
- Pins: `tests/errors/template_pins.json` entries for my new texts are marked "pending owner read".

## Tasks and models
| task | model | minutes |
|------|-------|---------|
| Items 1-3, 5-7 build and tests | Sonnet (this session) | ~75 |
| Pure text items 5, 8 | built inline by Sonnet, no Haiku helper started (each sat inside a test-first change) | n/a |
| Queue B items 8, 10, 12 | Sonnet (this session) | ~60 |
| Gate runs A (4 runs) | Sonnet (this session), commands only | ~95 |
