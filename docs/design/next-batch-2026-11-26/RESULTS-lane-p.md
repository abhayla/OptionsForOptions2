# Lane P results (26 Nov 2026) - first and second push

## PC set-up (do these first, in this order)

1. **Back up the database** (the PC's PostgreSQL is the live one): a full `pg_dump` of the app database, kept outside
   the repo; check the dump file is non-empty before going on.
2. `git fetch origin` and check out `feat/nb-plan-alerts-1126` at the pushed head.
3. Migrate: `python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head`.
   It runs `0054_actionable_alert_answers`, `0055_plan_stop_base` and `0056_several_standard_playbooks` (see "What the
   PC needs" below). Check afterwards: `alembic current` prints `0056_several_standard_playbooks (head)`.
4. Restart the API, the background worker supervisor (`python scripts/orchestrator/supervise_worker.py`) and rebuild
   the frontend (`cd frontend && npm run build`).
5. Post-migration checks: (a) Positions > Adjustment opportunities still lists the old records (rows written before
   0054 have no kind and are read as adjustment rules); (b) Alerts > Active opens and shows a number equal to the bell.
6. **Switching back to another branch afterwards is safe for runtime code.** Measured: the code at `e01f747` (before
   Lane P) run against a database migrated to 0055 passes its worker and store tests (test_background_worker 24,
   test_adjustment_opportunities 34, test_background_cycle 78, test_held_tracking 6, test_playbook_store 51 passed);
   0054's guard accepts a row without a kind from older code. One old-tree test fails by design
   (`test_alert_gate_storage`, the one that downgrades through old migrations), because an older branch cannot run a
   downgrade of migrations it does not know. Do not run `alembic downgrade` from an older branch; 0054's own downgrade
   refuses once new alerts exist (it would drop their answers).
   **0056, measured the same way:** the `e01f747` code run against a database migrated to 0056 passes
   test_background_worker 24, test_adjustment_opportunities 34, test_background_cycle 78, test_held_tracking 6,
   test_playbook_routes 18, test_system_playbook_versions 23, test_adjustment_plan 10. One old-tree test fails by design:
   `test_playbook_store.py::test_the_application_role_cannot_insert_a_system_row_and_the_owner_cannot_add_a_second`
   (50 passed, 1 failed, "DID NOT RAISE"): it expects the database to refuse a second standard playbook for one strategy
   type, and 0056 drops exactly that rule on purpose (ADR-330 (9), several standard playbooks). It checks a database
   refusal, not a screen path; the worker, store and plan routes of the old code all pass on 0056.

Branch `feat/nb-plan-alerts-1126`, cut from `fix/ic-live-test-1123` at `e01f747`. Standing-direction step: step 4 item 10
(defects that make the tracking journey wrong) for P1 to P3; "iron-condor depth (freeze lifted 2026-11-26)" for P4 to
P12. Highest status claimed for anything here: **Fixed, not tested** (the owner tests on his PC in market hours).

## Items

| Item | Status | Reviews | Notes |
|---|---|---|---|
| P1 one actionable-alert module + one info pop-up | Fixed, not tested | Opus round 1 REVISE (F1-F5, M1-M7) -> fix passes A and B; Opus round 2 closed all of them, found NEW-1 and NEW-2 (MAJOR) -> new item P1c; Opus check of P1c: SHIP (NEW-1, NEW-2, NEW-3 closed) | Wave 2 steps below; deferred #743 (held episode judged on the held step, pre-existing) |
| P2 only a strategy's own plan applies | Fixed, not tested | Sonnet: FIX (1 MAJOR, fixed inside P1b: plan-less strategies' open records close by system); 1 regression (A-27/A-35 test lacked a plan) fixed | |
| P3 stop amounts fixed at entry | Fixed, not tested | Opus round 1 FIX (F1 CRITICAL: T-06 still fired on the live max loss), round 2 SHIP | |
| P4 rupee plan levels | Fixed, not tested: complete with P4b (P4 itself was PARKED with N1 open after two rounds; P4b closed N1, Sonnet round 2 SHIP) | Opus round 1 FIX (F1-F9), round 2 SHIP on money with NEW N1 MAJOR (the levels preview drops the 2x-credit part while typing) | Both P4 merge commits are on the branch: "Merge P4 (ADR-330 (5), owner Q3) ..." and "Merge P4 Opus fixes F1-F9 ...". P4b (N1) is a new item for the second push |
| P5 plan time exit on any day | Fixed, not tested | Sonnet FIX (MAJOR: blank date used the playbook's time), fixed | |
| P6 max-loss line before a leg stop is saved (server) | Fixed, not tested (server only) | Sonnet SHIP + 3 minors fixed | the Stops panel line is Lane Q's PaperStops.vue |
| P10 Plan watch (server) | Fixed, not tested (server only) | not yet reviewed (Tier B) | PlanWatch.vue is Wave 2 |
| P11 Paper totals "Includes N closed strategies." (server) | Fixed, not tested (server only) | Sonnet SHIP + minors fixed | printing it is Lane Q's PaperStrategies.vue |
| P12 the "Strategies" menu label opens its menu | Fixed, not tested | Sonnet SHIP + minors fixed | |
| P4b levels preview keeps the 2x-credit part | Fixed, not tested | Sonnet round 2 SHIP | |
| LP-4 warning line, stop above the max loss (ADR-330 (25)) | Fixed, not tested | Sonnet FIX (paise tie, max loss <= 0, light expiry read) fixed | the browser prints `stop_warning` / `warning`; no Save is blocked |
| Alert titles with trade number and expiry (ADR-330 (19)(b)) | Fixed, not tested | Sonnet FIX (read failure must not stop the lists) fixed | `"Name" (#id, D Mon)`, or `(#id)` when no expiry is readable |
| P7 backend: side_closed alert after one side of an iron condor closes (ADR-330 (2), (33)) | Fixed, not tested (server only) | Sonnet round 1 FIX (4 MINORs), round 2: all fixed + ask again each closure | page flow is Wave 2; see deferred notes |
| P8 several standard playbooks (mechanism), Reset to playbook (ADR-330 (9), (32)) | Fixed, not tested (server only) | Sonnet FIX, round 2 fixed; P8b (a plan whose playbook was deleted keeps its own conditions) fixed | migration 0056; Reset button is Wave 2 |

## Owner and coordinator decisions used (all in ADR-330 or the owner-questions file)

Q2, Q2b, Q3, Q4, Q7, Q9, Q11 (owner, 26 Nov morning, all the plan's recommended option); LP-1 close by system when the
plan is removed (ADR-330 (3)); LP-2 a rupee stop replaces only the "% of max loss" part (ADR-330 (5); flag
`settings_in_force.RUPEE_STOP_KEEPS_CREDIT = True`); LP-3 (my B2 decision) the per-lot figure only when every leg has the
same lot count; LP-4 a rupee stop above the max loss shows one warning line and saves (ADR-330 (25)); LP-5 Reset to playbook keeps
the levels typed on the sheet (ADR-330 (32)); LP-6 ask again each time a side closes (ADR-330 (33)). Each is reversible in one place:
Q4 = `adjustment_readers.entry_batch` (first basket only); Q2 = frontend `bellCount` reads only `/alerts/active`;
Q2b/LP-1 = `actionable_alerts.close_by_system` callers in `background.py`.

## Deferred issues and open findings

#742 read-only routes reach order code through playbook_store (structural). #743 a held alert episode ends on the held step, not the rule's line (pre-existing, one held row per close after the daily cap). P1c MINORs: no test pins the browser's "watch.level." prefix to the Python constant; engine rule ids (stop.credit_x, plan.rupee_*, T-06, T-16, T-18) are not refused as user rule ids. Process: a builder killed an alembic process that held a DB session (the rule says never kill processes by name; recorded). Open MINORs listed for the owner: P3 NEW-1
(real-book entry with holdings adopted one by one), NEW-2 (ADR-266 check skipped at max loss exactly 0), a negative live
max loss raises inside the evaluator (pre-existing); P5 2027 calendar missing (step 3, #686); P1 M7 (shown_at back-dating
needs deliberate code), F7 of P3 (partly filled real entry reads "not checked").
Second push, open for the owner: (a) P7 marks a closure "over" only when the worker re-lists while the side has legs
again; legs added and closed again between two re-lists count as one closure. (b) Once a confirmed side re-opens, the
trade shows its entry shape name again (the builder went past its brief here; it follows ADR-330 (33), please confirm).
(c) The Adjustment-opportunities inbox heading for a side_closed row still reads "Adjustment opportunity detected"
(the Active row itself carries no adjustment wording). (d) Old-tree test above fails on 0056 by design.

## To file as deferred issues (coordinator files them; Lane P filed none after 17:17 IST)

| Title | Evidence | Spec basis | Done when |
|---|---|---|---|
| P7: a closure between two worker re-lists is missed | `side_closed.raise_if_closed` writes the `side_reopened` marker only when a re-list sees the side with legs again (builder report, P7 r2) | ADR-330 (33) "ask again each time" | legs added and closed again inside one cycle raise a new side_closed row; a test pins it |
| Inbox heading of a side_closed row reads "Adjustment opportunity detected" | `routes/adjustment_opportunities.py` group label falls back to that text when `source` is None | ADR-330 (2) (b), (3) | the inbox shows the side-closed wording, no adjustment heading; a route test pins it |
| P7 r2 test does not fail on the old `source` value | `test_a_side_closed_row_in_active_has_no_adjustment_wording` passes either way (builder note) | ADR-330 (3) | a mutation of `source` turns that test red |
| Browser "watch.level." prefix not pinned to the Python constant | P1c review MINOR | ADR-330 (4) | one test reads both and compares |
| Engine rule ids (stop.credit_x, plan.rupee_*, T-06, T-16, T-18) accepted as user rule ids | P1c review MINOR | ADR-330 (3) | a user rule with such an id is refused naming the field |

## Hand-over (Lane P stops after the second push; Lane J takes the page work)

DONE (server, Fixed, not tested): P1, P1c, P2, P3, P4, P4b, P5, P6 server, P7 backend, P8 mechanism + P8b, P10 server,
P11 server, P12, LP-4 line, alert titles; migrations 0054, 0055, 0056 with old-code proofs above.
LEFT (Wave 2, the steps below): paper_monitor `_fire` -> inform + P6 line + stop titles; AlertsPage Exit -> usePaperExit;
PaperStops leg-stop-risk line; PlanWatch.vue; PaperStrategies closed_text; P7 page flow (two answers + "Not applicable"
line, needs a reply field and an owner-approved inventory note); P8 Reset button and change markers.
OPEN FOR THE OWNER: the three second-push points under "Deferred issues and open findings".

## Wave 2 steps left (for the lane that joins with the screens line)

1. `backend/ofo_app/paper_monitor.py` `_fire` (~:238): replace `triggers.add_alert(...)` with
   `actionable_alerts.inform(conn, user_ref, strategy_id, "stop_fired", <template_id>, values, at=...)`, and add the P6
   line (reuse `routes.paper._stop_line` / `_exit_warning(..., leg_stop=True)`) to that message; then remove the guard
   exemption `("paper_monitor.py", "_fire")` in `tests/test_actionable_alert_one_module.py`.
2. `frontend/src/pages/AlertsPage.vue` Exit button: open the shared paper exit confirmation (`usePaperExit`, refactor
   Phase 4) instead of navigating to `/strategy/builder?strategy=<id>` (comment "WAVE 2" marks the line).
3. `PaperStops.vue` (Lane Q): call `GET /api/paper/strategies/{id}/leg-stop-risk?contract_id=&level=` when a leg and a
   valid level are typed; print `warning_text` when `state == "yes"`, nothing otherwise; Save always enabled.
4. `PlanWatch.vue` (new) mounted in `StrategyBuilderPage.vue` and `PaperStrategies.vue`, reading
   `GET /api/strategies/{id}/plan-watch` (shape in the P10 notes: `plan_state`, `no_plan_text`, `armed_heading`,
   `lines[]` of `{key, kind, section, label, unit, fires_at, now, distance_rs, distance_pct, state, reason}`).
5. `PaperStrategies.vue` (Lane Q): print `totals.closed_text` beside the left-out line (P11).
6. P7 page flow: the side_closed row's two answers `add_legs` / `confirm_new_shape` (POST `/api/alerts/{id}/answer`),
   and the "Not applicable: the <side> side is closed" line (needs a new reply field, so a reply-inventory note).
7. P8 "Reset to playbook" button: POST `/api/strategies/{id}/adjustment-plan/reset` after one confirmation that says
   the typed levels stay (ADR-330 (32)); show `changed` / `switched_off` markers from the plan reply.
8. Stop-alert titles in `paper_monitor.py` with the same `"Name" (#id, D Mon)` form.

## What the PC needs to test this branch

- **Migrations: three.** `0054_actionable_alert_answers` adds to `public.adjustment_suggestions` the NULL
  columns `kind`, `answer`, `answered_at`, `no_longer_true_since`, `escalated_at` with CHECK lists, replaces that
  table's guard trigger function (old rows keep NULL and are read as adjustment rules) and widens the app role's column
  grants for them. `0055_plan_stop_base` adds `stop_base JSONB NULL` to `public.strategy_adjustment_plans` and its
  grant. No row is changed or deleted by either. Note: once new alerts exist, 0054's downgrade refuses (it would drop
  their answers); treat it as one-way. Run: `python scripts/orchestrator/db_run.py . python -m alembic -c
  backend/ofo_app/alembic.ini upgrade head`.
  `0056_several_standard_playbooks` drops the one-standard-playbook-per-type unique index, adds a `slug` column (each
  standard playbook gets `<type>-default`, unique) and adds its allow-list entries. No playbook or plan row is deleted.
- **Restart** the API and the background worker (supervisor) after pulling; rebuild the frontend (`npm run build`).
- No new environment variable.

## Click-by-click screen checks (owner, market hours)

P1 alerts (ADR-330 (3), (4)):
1. Open a paper iron condor WITH a plan. Wait for (or arrange) the plan's loss stop to be crossed.
2. Expect a short pop-up that disappears by itself (about 6 s) and the bell number goes up by 1.
3. Open Alerts > Active: exactly as many rows as the bell number. The row shows "Fired at HH:MM" and two buttons:
   "Exit the position" and "Continue with the position". Opening the page does not lower the bell.
4. If the loss comes back inside the stop, the row stays and adds "no longer true since HH:MM"; when it crosses again,
   that line goes away. If the loss gets worse, a second pop-up says "Worse than when it fired: ...".
5. Press "Continue with the position": the row leaves Active, the bell drops by 1, Alerts > History shows the answer and
   its time. Nothing is exited.
6. On another alert press "Exit the position": the answer is stored and the builder page of that strategy opens; the
   exit itself is still your own click on the usual exit confirmation.
7. Exit a whole paper trade that has an unanswered alert: History shows "Closed by system: the trade closed at HH:MM"
   with the trade's own close time.
8. A fired leg stop or index exit (Stops panel) shows only a pop-up and a History record; it is never counted on the bell.
9. A watched level (Watch this level) still gives one record per crossing (not on the bell).

P2 no plan, nothing watched (ADR-330 (11)):
1. Open a strategy with no plan: the plan card reads "No plan: nothing is watched for this strategy".
2. No adjustment suggestions and no target/stop alerts appear for it; its Stops-panel exits and leg stops still fire.

P3 stop fixed at entry (ADR-330 (1)):
1. Enter an iron condor, save a plan; note the plan's stop line, e.g. "15.4 % of max loss (Rs 400.40)" and "2x credit
   Rs 7,800".
2. Close the call side (two exits). Reopen the plan: the same Rs 400.40 and Rs 7,800 (not 756.76 / 3,172).
3. The stop alert fires at that same rupee loss.

P5 time exit on any day (ADR-330 (7), Q9):
1. Plan sheet: the field reads "Time exit" with a date box (blank = expiry day).
2. Set today's date and a time 5 minutes ahead; save. At that time an alert appears (P1 behaviour); nothing exits.
3. A weekend, a holiday, a past date or a date after the last expiry is refused naming the field.

P6 leg-stop line (server only today): in the browser open
`/api/paper/strategies/<id>/leg-stop-risk?contract_id=<short leg contract id>&level=<price>` - expect a JSON whose
`warning_text` reads "If this stop fires, max loss becomes Rs X (now Rs Y)." The Stops panel line comes with Lane Q.

P10 Plan watch (server only today): `/api/strategies/<id>/plan-watch` returns one line per trigger; a strategy with no
plan returns the P2 sentence and still lists its armed Stops-panel triggers.

P11 (server only today): `/api/paper/strategies` totals carry `closed_text` "Includes N closed strategies." when the
list hides N closed ones.

P12 top menu: on My Strategies, click the word "Strategies" in the top menu: its menu opens; click again: it closes. On
another page the same click goes to My Strategies. Ctrl-click opens a new tab.

P4 rupee levels (ADR-330 (5)): the plan sheet has "Target (Rs)" and "Stop (Rs)" boxes. Type 400 in "Stop (Rs)" on a
1-lot iron condor with max loss Rs 2,600: the percent box fills with 15.38 (from the server) and the line under it reads
"a loss of Rs 400.00 (15.38 % of max loss), 2x the credit received ... whichever comes first" - the same sentence the
saved plan shows after Save. Exactly one stop alert fires when the loss reaches Rs 400.

LP-4 (ADR-330 (25)): on the same trade type 3000 in "Stop (Rs)": one line under the box reads "This stop (Rs 3,000)
is above the trade's max loss (Rs 2,600), so it cannot be reached." Save still works. Type 400 again: the line goes.

Alert titles (ADR-330 (19)(b)): open two paper trades with the same name; raise an alert on each. Alerts > Active shows
`"Short Iron Condor" (#12, 9 Dec)` and `"Short Iron Condor" (#13, 9 Dec)` style names (trade number, nearest expiry);
History shows the same after an answer. A trade with no open leg shows `(#id)` only.

P7 (server only today): on a paper iron condor with a plan, exit both call legs. Within one worker cycle Alerts > Active
gains one row naming the closed side (it counts on the bell). Answer it via the Active row's buttons when Wave 2 lands;
today, `/api/alerts/active` lists it with kind `side_closed`. Exit the put side of a different trade: one row too.

P8 (server only today): POST `/api/strategies/<id>/adjustment-plan/reset` on a plan saved from a playbook: the reply's
conditions match the playbook again, the stop / target rupee levels typed on the sheet stay, `changed` is empty. On a
plan whose playbook was deleted the reset is refused with the playbook's not-found sentence, and saving that plan's
rules unchanged still works.

## Process notes (counters)

- Claims later found false: P2 round 2 reported "215 files passed" while A-27/A-35 were red; P1b round 2 left 14 vitest
  fixtures red; per-builder sweeps missed 8 failing tests_app files that one full run found. Fix applied: a full
  tests_app and domain run before the push.
- The auto-mode permission check refused writing reviewer notes in tests_app/reply_inventory.py and the order-closure
  pins; both wait for the owner's own words (not worked around).
- This container has no Windows VPS tunnel: DB tests ran on a local PostgreSQL 16 set up as CI does (app role
  `ofo_app`, migrations as the owner role).
