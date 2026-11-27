STATUS 17:45 | items 1,2,3,5,6,7: Fixed, not tested; item 4: parked | next push 18:30 (A) | blocker: none (send_message to @parent refused: session not trusted, this line is the report)

# Lane O results (branch fix/alert-screens-1127, cut from bcbff80)

Highest status used: "Fixed, not tested". Nothing is approved until it passes on the owner's PC.
Tests ran locally on a throw-away PostgreSQL 16 in the container (not the owner's tunnel).

## Queue A

| # | Item | State | Test (first failing, now passing) |
|---|------|-------|------------------------------------|
| 1 | T2-19 Reset markers | Fixed, not tested | tests_app/test_adjustment_plan.py::test_reset_to_playbook_...; frontend/tests/plan-reset-p8.test.js |
| 2 | Alert row reason = trade name only | Fixed, not tested | tests_app/test_alert_routes.py::test_an_alert_with_no_worded_condition_shows_its_rule_not_the_trade_name |
| 3 | History error over a loaded list | Fixed (placement), cause of the failing request not proven | frontend/tests/alerts-history-d22.test.js (item 3) |
| 4 | Compare approaches "Now" label | PARKED | see below |
| 5 | Stop sentence date style | Fixed, not tested | tests_app/test_plan_watch.py::test_planned_condor_lines |
| 6 | Armed stop sentence | Fixed, not tested | same test, plus the paused test |
| 7 | Draft shows "strategy was not found" in Plan watch | Fixed, not tested | tests_app/test_plan_watch.py::test_a_just_saved_draft_reads_as_no_plan_never_not_found |

### Core proof (item 1)
Before code: the real reset route answered no `put_back` field and the reset reply always had empty
`changed` / `switched_off` (a reset puts every condition back, so the old marker lines were empty by design, hence "not shown").
Fix: the reset reply now names what the plan differed in just before the reset (`put_back`, `put_back_off`), and the sheet prints it
with server-sent labels. Files touched outside my list: `AdjustPlanSheet.vue` (the Reset marker block only; the plan sheet is Lane V's, so merge carefully) and `adjustment_plan.py` (reset route only; Lane R2 owns plan read/save).

### Screen steps (market CLOSED is fine)
1. T2-19: open a trade with a plan, Customise triggers, switch off T-05 and change another condition, save. Open the plan sheet, press "Reset to playbook", confirm. Expected under the button:
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

### Item 3 note
I could not tell which request failed on the owner's PC. Likely cause [guess]: `/alerts/answered` takes longer than the browser's 10 s limit because `alert_title.labels` reads the nearest expiry once per distinct trade. List for Lane J / deferred issue below.

### paper-only path found
None met in the files I changed.

## To file as deferred issues
- History `/alerts/answered`: per-trade expiry read may exceed 10 s with many trades (measure).
- Item 4: source of the "Now" value in the opportunities list (needs Lane J).
- Pins: `tests/errors/template_pins.json` entries for my new texts are marked "pending owner read".

## Tasks and models
| task | model | minutes |
|------|-------|---------|
| Items 1-3, 5-7 build and tests | Sonnet (this session) | ~75 |
| Pure text items 5, 8 | built inline, no helper started (tiny change inside a test-first change) | n/a |
