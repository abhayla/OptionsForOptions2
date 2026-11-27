# RESULTS: Lane W, 27 Nov 2026 (small fixes from the live market test)

**SAFE TO CLOSE** (Lane W, 27 Nov). Code head 09923e9 (item 15); this RESULTS commit sits on it; push 2 carries both
through the pre-push gate. Leftovers: items 5 and 6 (Lane J's files, change notes below), item 12 wording (owner),
SPEC CHANGE REQ-112 AC-2 (owner), item 15's three owner points, the deferred list at the end.

Branch `fix/live-test-small-1127`, cut from `origin/integration/nb-1126` at 206a9f0. No PR, no migration, paper only.

## Status lines (send_message to the parent and to the coordinator session was refused:
`elevated_session_untrusted_device`; the lines are kept here instead)
- LANE W ALIVE (27 Nov, branch cut from 206a9f0)
- 12:55 IST: item 14 (coordinator message 12:50, S-11: Customise triggers then Back drops the typed plan) taken.
- 13:18 IST coordinator: item 14 dropped (PC re-ran T3-16 at 13:04: PASS; the 12:42 failure was the sheet taking 17 s
  to load). Its commit is reverted; noted only as "plan sheet loads slowly" (deferred 9). Asked for a docs push now:
  a docs-only push needs its own gate run (~35 min), the same as the full tree, so the first push carries every item.
- Push 1 (27 Nov ~15:05 IST): head 022c108, prepush TOTAL PASS (1872 s, app_tests and frontend_unit included),
  items 10, 11, 8, 1, 2, 3, 4, 7, 9, 13 (+ 5, 6, 12 notes; 14 reverted).
- 14:33 IST coordinator: item 15 (HIGH, T2-10: Add to Paper accepted 5000 lots). Done with an Opus review, round 2.
- Push 2: item 15 + this RESULTS (head and gate below in git log; gate run on the RESULTS head).

## Items

New wording is marked **pending owner read**; every such sentence is also pinned "pending owner read" in
`tests/errors/template_pins.json` when it is a server template.

| # | Status | RCA (one sentence) | Fix | PC click steps |
|---|---|---|---|---|
| 10 | DONE (Tier A, Opus review: FIX-FIRST, both fixes applied) | "Open in builder and prepare basket" POSTed `/adjustment-opportunities/{id}/acted-on` at STAGING, and acted_on is final in the DB, so a cancelled basket stayed "Acted on". | AdjustCompare posts nothing; `playbook_store.link_orders` stamps an OPEN record acted_on inside the paper placement transaction (only an accepted placement stamps). A record that is dismissed, lapsed, already linked, missing, foreign or another strategy's is SKIPPED, never a refusal (an exit is never blocked by a record's state); the record read is locked (`FOR UPDATE OF g`). `routes/paper.py` not edited. | Alert, Compare approaches, "Open in builder and prepare basket", Cancel: the opportunity still reads "Open". Prepare again and Confirm: it reads "Acted on - Paper - not sent to Zerodha". |
| 11 | DONE | A full-exit prepare stages exits via `exitAllPaper()` which calls `setLegs([])`, and LegList chose "No legs yet" from `legs.length` alone. | `emptyListKind` in `lib/legEdit.js` (one module); LegList shows the held legs as exiting; a failed read says nothing about legs; opening shows the opening card. New: "Exiting these legs (staged, not placed yet)" **pending owner read**. | Alert, Compare, full-exit approach, "Open in builder and prepare basket", Cancel on the confirm list: the held legs show as exiting with "N pending changes", never "No legs yet". |
| 1 | DONE | `totalCell` in `lib/paperPnl.js` dropped `totals.closedNote`, so Home never printed the server's line. | Home prints the same `totals.closed_text` from the same reply (`GET /paper/strategies`, `_closed_text()` in routes/paper.py, unchanged); no second count. | Home with closed strategies: the line under "Total P&L (after charges)" reads the same "Includes N closed strategies." as Positions. |
| 2 | DONE | The History row printed `answer_label` ("Closed: the position ended") first, so the server's `closed_reason` never showed. | AlertsPage shows `closed_reason` when present; the server text already was ADR-330 (3)'s "Closed by system: the trade closed at HH:MM". A system-closed alert leaves Active by design, so only History shows it. | Alerts, History, an alert whose trade closed unanswered: "Closed by system: the trade closed at 10:23". |
| 3 | DONE | T-10b always carried the playbook stage label ("Clock time reached"), and the plan sheet's refusals went through `playbook_body_invalid` with the raw field name. | `trigger_words` / `condition_line` (backend/ofo_app/adjustment_check.py) name the plan's time exit; a playbook clock rule keeps "Clock time reached". `plan_sheet_invalid_<box>` templates name the box label (14 of 18 `_bad()` sites named a box by its code word; all 14 fixed; the other 4 are not sheet boxes). New, all **pending owner read**: "Time exit reached: the plan's time exit is 11:03"; "Time exit date is in the past."; "Time exit date is not valid."; "Time exit is not valid."; "Target is not valid." (same for Stop, Target (Rs), Stop (Rs), Max adjustments). | Plan sheet: a past time-exit date, Save: "Time exit date is in the past." Set a time exit 2 min ahead: the alert reads "Time exit reached: the plan's time exit is HH:MM". |
| 6 | NOT FIXED, Lane J's file | The stop line is built in `backend/ofo_app/routes/plan_watch.py:242` with `describe_contract` (ISO date). | For Lane J: `leg = display_contract(identity)` instead of `describe_contract(identity)` there. Other ISO users of `describe_contract`: paper.py 7 calls, adjustment_history.py:215, reconciliation/* 10, strategy/versions.py 4 (see deferred). | - |
| 4 | DONE | `build_from_catalogue` let `StrategyDefinition` raise a plain `DefinitionError` for a repeated contract, which mapped to the generic "cannot be saved as sent". | New `DUPLICATE_LEG` refusal with typed slots, contract via `display_contract`. The rule is on the contract alone (a Buy and a Sell on one contract are refused too), so two sentences, **pending owner read**: same side "Legs 1 and 2 are the same contract and side (NIFTY 1 Dec 25900 CE, Sell)." / "Join them into one leg with more lots, or change one of them."; opposite sides "Legs 1 and 2 are the same contract (NIFTY 1 Dec 25900 CE), one Sell and one Buy." / "A strategy holds one leg per contract: remove one of them, or change one to a different contract." | Builder: two legs on one strike and expiry, Save draft; once same side, once opposite sides. Check the leg numbers match the screen. |
| 8 | DONE | The right-hand "No draft strategy is open. Add a leg to start one." was chosen by `state === 'no-draft'` alone and never read `paperCompleted`. | `emptyListKind` gains a `closed` kind; new "This trade is closed. Its legs and result are shown below; it cannot be changed." **pending owner read**. | My Strategies, a Completed trade, Open in Builder: the new sentence on the right; a running trade and a fresh builder keep their text. |
| 9 | DONE | AlertsPage fell to the empty state whenever there were no rows, also before the first read returned. | "Loading..." (the app's existing text) until `activeAlerts.loaded`; a failed read keeps the error text. | Alerts, Active on a slow connection (dev tools, Slow 3G): "Loading..." then the rows. |
| 5 | NOT FIXED, Lane J's files | A draft has no running trade, so `tracked_reader` returns None in `adjustment_check.run_check` (~line 494), which raises `StrategyRefused(NOT_FOUND)`, a 404 that `plan_watch.py:266` passes on; `lib/planWatch.js:66` turns every 404 into "not found". | For Lane J: in plan_watch.py, before `run_check`, a strategy that exists and is a DRAFT gets 200 with a new `plan_state` "not_started" (add to the Literal ~line 94), `lines: []` and a server text such as "Plan watch starts when this strategy is added to Paper." (**pending owner read**); a missing or foreign strategy keeps the 404. planWatch.js: add "not_started" to `PLAN_STATES` and show the server text as `no_plan` does. Tests: route draft -> 200 not_started, unknown id -> 404; planWatch.js parse test. | - |
| 7 | DONE | The My Strategies rename form never focused its input, and Modal focused the dialog frame, not the field. | Modal focuses a `[data-autofocus]` field on open (Save, Save As, Update Strategy Name); the My Strategies row rename focuses via `nextTick`; Esc closes from open. | My Strategies, Rename on a row, type at once: the text goes in; Esc closes. Same with Builder, Save. |
| 12 | NO CHANGE (wording is the owner's) | The spec gives an exact sentence for one take-profit refusal only, and the app already matches it. | Spec vs app: not_in_profit: ADR-238 (6) has only the fragment refused "not in profit" / app "The whole trade is not in profit with every open leg closed at its planned price, so this approach is not built."; not_in_profit_after_charges: ADR-326 (1) "Not in profit after charges: {after}" / app the same; booked_unknown, two_expiries, charges_unknown: no spec sentence. Aligning to ADR-238's bare words is a wording decision (about 20 fixtures pin the current sentence). | - |
| 13 | DONE | The Contract cell and header of Net Positions had no `nowrap`. | `whitespace-nowrap` on both (PaperBookPanel.vue); the existing `overflow-x-auto` wrapper scrolls the table inside its box. A class check only: check by eye. | At 1366 px, a paper strategy with an open position, Net Positions: "NIFTY 1 Dec 25900 CE" on one line. |
| 14 | DROPPED (coordinator 13:18) | Not a defect: the plan sheet took 17 s to load at 12:42; at 13:04 the typed 400 and 15:15 stayed (T3-16 PASS). | Commit 931562e reverted. | - |
| 15 | DONE (Tier A, Opus review: FIX-FIRST, round 2 applied) | `place_paper_orders` (the one paper order door) never called the lots check (`check_lots`, REQ-167 AC-5 `limits.max_lots`) or the freeze check (ADR-081/ADR-092), which lived only in the order review and leg-edit routes. | `_refuse_legs_over_limit` in routes/paper.py (~1371, called ~1426), one check for every non-exit order (Add to Paper, Add Selected, Increase quantity, Change expiry all post through `addToPaper` to this route): refused when lots exceed `limits.max_lots` or units are not below the stored freeze limit (the same rule as freeze.py:73 / leg_edit.py:295); fails closed if settings or the freeze store fail; nothing half-written (a Change expiry exit+add is refused whole). New, **pending owner read**: "NIFTY 1 Dec 25900 CE asks for 5000 lots; the most one order can hold is 53 lots."; "The exchange limit for NIFTY 1 Dec 25900 CE is smaller than one lot (50 units, lot 65), so it cannot be ordered." | Settings: check a NIFTY freeze limit is stored (without one only `limits.max_lots`, default 10000, applies). A draft, one leg at 5000 lots, Add to Paper: the sentence, nothing in the book. At the limit minus one lot: accepted; at the limit: refused. Same with Increase quantity in Drafts Mode. |

## SPEC CHANGE pending the owner
- Item 15, three points for the owner: (a) with NO freeze limit stored for a contract the paper order is not
  refused (ADR-081: the review warns); a hard refuse would be a SPEC CHANGE. If the PC has no freeze rows loaded,
  5000 lots still pass up to `limits.max_lots` (10000). (b) Paper EXITS are not checked; ADR-092 says the block covers
  every order the platform prepares: SPEC CHANGE (departs from ADR-092 "every order"), chosen so an exit is never
  blocked. (c) The check is per order: open 8 lots then add 8 with max_lots 10 is accepted (the leg holds 16).
- Gate fixes added, **pending owner read**: two slot types `ContractName`, `SideWord` (gate_slots.py, pinned in
  tests_app/test_identifier_and_slots.py) for item 4; two sentences "Target and Target (Rs) show different values."
  and "Stop and Stop (Rs) show different values." (templates 710/711) for a plan sheet whose two boxes disagree.
- REQ-112 AC-2 said "Acted on" meant "prepared a basket"; item 10 (coordinator brief: stamp only on a placed order)
  contradicts it. The AC text now says a paper order must be placed. Owner to confirm.

## To file as deferred issues
1. Item 6 (Lane J): `plan_watch.py:242` `describe_contract` -> `display_contract`. Class: server texts naming a
   contract with an ISO expiry through `describe_contract`: paper.py 7 calls, adjustment_history.py:215,
   reconciliation/* 10, strategy/versions.py 4; many frontend fixtures carry ISO `contract_text`.
2. Item 5 (Lane J): the draft plan-watch state, change note in the table above.
3. ADR-330 (3) plan-removed close: no plan-removed close reason or sentence exists; a plan removal falls under
   "not_monitored" ("The strategy is no longer monitored"). Needs a reason code and the decided sentence.
4. Item 4 class: other causes still get the generic "This strategy definition cannot be saved as sent.": 7
   `StoredFormError(INVALID_DEFINITION, ...)` sites plus every `DefinitionError` mapped by `_definition_refused`
   (no legs or above the leg cap, a futures leg with a strike, bad strike or quantity, an action not Buy/Sell, a
   malformed leg, one contract id twice in `SavedDefinition`); also MALFORMED, NOT_DECIMAL_STRING, LIVE_STATE_FIELD.
5. Item 10 leftovers (Opus review): (a) rows stamped at staging under the old code whose basket was cancelled stay
   "Acted on" for good (the 0054 trigger blocks a change back); a later placement links them. (b) The `opp=` ids
   stay in the URL after Cancel or Discard, so a later hand-built basket on that page links them with the prepared
   basket's `basket_legs` (older than this change). (c) A strategy with only a plan and no paper book places through
   SaveDraftBar with `[]` ids, so its record is never stamped (only matters if records can exist there). (d) The
   `/acted-on` route still exists for other callers; nothing in the frontend calls it.
6. `tests_app/test_adjustment_history_why.py` and 11 tests of `tests_app/test_adjustment_opportunities.py` fail in
   the cloud container on 885823c too (the check reports `already_true`, not `flag`, so no record opens: a clock
   issue); item 10 edited assertions there that have not run green here. Run on the PC.
7. Item 13: the nowrap is checked by class only; needs a rendered-width check.
8. Two new codes STRATEGY_VALIDATION_524/525 (item 4) may collide with another lane's numbers at merge.
10. tests_app order dependence: `test_adjustment_plan.py::test_core_use_as_is...` leaves an edited active playbook in
   the shared test DB; with file order reversed it fails itself (prefill returned playbook 3, not "Core own" 14).
   Item 10's test no longer depends on it (plans from the system playbook).
9. Plan sheet loads slowly (17 s at 12:42 on the PC, 27 Nov): the cause of the item 14 report.

## Task | model that did it
| Task | Model |
|---|---|
| Item 10 build, rounds 1, 2, 2b | Sonnet builder |
| Item 10 Tier A review (Why Opus: the stamp moved into the paper order placement transaction, the exit path) | Opus reviewer |
| Item 11 | Sonnet builder |
| Item 8 | Sonnet builder |
| Items 1, 4 | Sonnet builder |
| Items 2, 3, 6 (6 investigation only) | Sonnet builder |
| Items 7, 9, 13 | Sonnet builder |
| Items 5, 12 (investigation; no code) | Sonnet builder |
| Item 14 (later dropped, reverted) | Sonnet builder |
| Pre-push fixes: duplicate-leg test move, selector pin, ruff findings | Sonnet builder |
| Ruff E501/I001 rewrap after the item 10 merge | Haiku builder |
| Gate app_tests fixes (slot pin, plan rupee-level refusal tests) | Sonnet builder |
| DB-order fix of the item 10 test, target-refusal test | Sonnet builder |
| Item 15 build, rounds 1 and 2 | Sonnet builder |
| Item 15 Tier A review (Why Opus: a refusal inside the one paper order door) | Opus reviewer |
| Splitting, routing, cherry-picks, conflict resolution of template_pins.json, revert of item 14, verification runs, RESULTS | main session (Opus) |
