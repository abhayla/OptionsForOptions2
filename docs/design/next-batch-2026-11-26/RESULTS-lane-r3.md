STATUS 22:15 | items 1, 2, 3, 4: Fixed, not tested | PUSHED head 7da2e173 (gate TOTAL PASS, one push for all four items) | blocker: none (messages to the coordinator refused: untrusted device; this line is the report)

# Lane R3: plan reads and the live check use the stored expiry kind (hotfix/plan-read-2-1127)

Spec basis: ADR-330 (1) (stop base and the stop the checks read), (5) (a base that cannot judge refuses), (9) and (32) (Reset to playbook puts back the conditions only), (58) (paper and real the same), ADR-252, ADR-003.
Base: origin/hotfix/plan-read-1127 1d0f56e (+ merge of origin/chore/gate-speed-1127). Nothing here is approved until it passes on the owner's PC.

## Bad news first
- **HIGH, for Lane J2 (not mine):** with a far-month leg whose own future is not listed (kind now "not known"), the worker's alert-style step raises and the strategy is paused with CHECK_FAILED BEFORE any rule is evaluated: the rupee-level stop and the time exit (which need no kind) do not run either. Before this change those legs were read as weekly (wrong row) and evaluated. Fail closed is right for the percent stop, but it should not drop the kind-free rules. See "For lane J2".
- The kind cannot be known for a leg past the last listed future (e.g. 30 Mar 2027 with futures 24 Nov, 29 Dec, 26 Jan). It reads "not known" until that month's future is listed: the percent stop of such a trade is "not checked" (shown as such), and the sheet shows no stop with its reason. The rupee stop is unaffected.
- The scratch database has role pins that fail on any branch (`test_core_use_as_is_copies_the_active_playbook...` fails on the base too). The wide run of 77 files has 160+ failures on the base as well (role grants, shared scratch state); the same 21 files on the base commit fail the same way. CI's database is the check.

## Core and proof (item 2)
Core: the position of a stored trade carries its expiry kind from the stored catalogue, by the ONE rule (`expiry_kind_of`), so the live check, the plan sheet and every reader agree. Proof BEFORE any fix (`tests_app/test_plan_read_2_1127.py`): a stored monthly trade (leg day = a future day) read through the real `_tracked_on`: `assert tracked.position.expiry_kind == "monthly"` failed with `'' == 'monthly'`; a stored weekly trade the same; far month and no-future cases answered `'weekly'` where `''` is right. 6 red of 9. After the fix 11 green (stop 30 % read for the monthly trade, 50 % for the weekly one, with no market kind).

## What changed
| Item | Change | Test |
|---|---|---|
| 1 | `expiry_kind_of` (adjustment_readers.py) answers "" (not known) when no future is listed or the expiry is after the last listed future; monthly = a future's day; weekly inside the futures; a scenario's stated kind wins. The plan route's `_stored_kind` now only calls it (via `stored_kind`), so R2's far-month rule is no longer a second copy. | `test_a_far_month_with_no_future_of_its_month_is_not_known_not_weekly`, `..._no_future_listed_at_all_is_not_known`, `..._inside_the_listed_futures_is_still_read`, `..._scenario_that_states_the_kind_wins` |
| 2 | `_tracked_on` sets `Position.expiry_kind` from the stored catalogue (`stored_kind`), read BEFORE the stop-base backfill write. `state_of`, `exit_inputs_of`, `money_inputs` no longer default to "weekly": with no kind the stop lines are None (not checked), `days_left` is None (no stage, no T-09), and no approach is priced. | `test_a_stored_monthly_trade_reads_the_monthly_row_with_no_market_kind`, `..._weekly_trade_reads_the_weekly_row`, `test_a_kind_that_cannot_be_known_checks_no_stop_and_never_reads_weekly` (2 cases), `test_a_catalogue_read_that_fails_leaves_the_kind_empty`; `test_stop_base_fixed.py` market now states its kind |
| review | The kind is read for the NEAREST leg (the check counts days to it), not `legs[0]`. The entry state (`_entry_state`) keeps no day count when the kind is not known. | `test_the_kind_is_read_for_the_nearest_leg_not_the_first_one_ordered`, `test_the_entry_state_has_no_day_count_when_the_kind_is_not_known` |
| 3 | Lane O's patch (Reset names what it put back, T2-19) merged by hand: `put_back` / `put_back_off` on the reset reply, read from the diff BEFORE the copy goes back; sheet shows them. Read against (9) and (32): conditions only come back, typed levels stay (the patch does not touch them). Conflicts were only with R2's `_kind_of` replacement (now `row.kind`, `row.reason`) and R2's `stop_kind_reason`. | `test_adjustment_plan.py` reset test (names `triggers.T-06`, empty lists on a second reset and on a plain GET), `plan-reset-p8.test.js` |
| 4 | Test only, no code needed: a save whose answer never reached the browser reads back complete. | `test_a_saved_plan_whose_answer_was_lost_reads_back_complete_on_the_monthly_row` |

Item 4 result: after a save (answer discarded as a timeout would), `GET plan` returns the same `triggers`, `settings`, `stops`, `triggers_reason`, `stop_kind_reason` as the save answer, with stop 30 (monthly row) and the saved target, twice the same. Not reproduced: a rules/exits read failure on the server. What OBS-26 saw as "exits could not be read back" is most likely the paper-only exits read below (`/paper/strategies/{id}/triggers`), which a real-mode trade has no equivalent of. Listed, not fixed (not my file).

## Opus review of items 1 and 2 (stop path)
Why Opus: stop path. One independent review, verdict REVISE, round 1 used.
| Finding | Result |
|---|---|
| MAJOR worker pauses (CHECK_FAILED) before kind-free rules when kind is unknown (background.py:1505) | Not mine: "For lane J2". |
| MAJOR kind read from `legs[0]`, the check counts days to the nearest leg | Fixed (readers, plan route) + test. `background.py:356` has the same `legs[0]`: "For lane J2". |
| MINOR entry state kept a weekly day count with no kind | Fixed + test. |
| MINOR rollback in the catalogue read discards the same session's backfill | Fixed by reading the kind before the backfill. |
| MINOR full catalogue loaded per strategy per read | Listed (cache if it shows). |
Reviewer held: no `or "weekly"` left in the changed files; `approaches.py:475` guarded; T-09, limits and the stop answer refuse with days_left None; paper and real both pass the kind.
Note from the reviewer (spec silent): beyond the last future only monthly or quarterly contracts list, so "not known" holds back a stop that is really monthly for up to about 3 months. Owner decision needed if that is too long (see "To file").

## For lane J2 (`backend/ofo_app/background.py`)
1. Line ~1505, `style = alert_presets.style_for(state.expiry_kind, state.days_left, pin)`: with `state.days_left is None` (kind not known) it raises and the strategy is paused before the rules run. Guard it: `if state.days_left is None: style = <the default style of the strategy's pin, or skip the style step>` so `pe.evaluate` still runs the kind-free rules (rupee stop T-06 in rupees, time exit).
2. Line ~356, `expiry = position.legs[0].expiry` in the market input: use `min(x.expiry for x in position.legs)` as `adjustment_readers.read_market` now does for the kind. Same at ~880 and ~1217 if they feed a kind.
3. The worker's `_tracked_on` read now loads the catalogue once per strategy (the position's kind). If that shows in the hold time, pass the kind from the worker's own read (`expiry_kind_of(expiry, read.listed, read.futures, scenario)`) into `Tracked` after the read, as `as_of_market` does.

## Paper-only paths found (ADR-330 (58))
- `frontend/src/components/strategy/PlanEntry.vue:65` and `frontend/src/lib/paperTriggers.js:5`: the exits (armed/fired) come from the paper route `/paper/strategies/{id}/triggers`; no real-mode read. Not changed (not my file; Lane K owns routes/paper.py). Likely the cause of OBS-26's "exits could not be read back" for a real trade.
- In my files: none.

## To file as deferred issues (not filed by me)
1. Worker: alert style raises when the kind is unknown and pauses before kind-free rules (stop path, HIGH) and `legs[0]` vs nearest leg in `background.py` (see J2).
2. `_tracked_on` loads the full live catalogue per strategy per read; use the market's kind when present or cache.
3. A far month whose own future is not listed stays "not known" up to about 3 months; a rule for such months (the last listed option expiry of the month, as before) needs an owner decision.
4. The "not checked" reason for a trade with an unknown kind says the days left are missing (the engine's own code): a kind-specific reason code needs a change in `ofo/adjustment/playbook_eval.py` (not mine).
5. `AdjustPlanSheet.vue` still does not show `stop_kind_reason` (R2's item 5, still open; not in my queue).

## Why one push (gate TOTAL PASS on the pushed head)
The gate runs about 18 minutes and each push needs a TOTAL PASS on a clean tree; items 3 and 4 were ready before the first gate finished, so the four items go in one push to save a second gate run (hotfix/plan-read-2-1127 only, no PR).

## Tasks, models, minutes
| Task | Model | Minutes |
|---|---|---|
| Read, failing tests, fix items 1, 2, 4, merge Lane O patch (item 3), scratch DB, baseline comparison, gate | Sonnet (this session) | about 150 |
| Independent review of items 1 and 2 | Opus (reviewer agent) | 5 |
| Mechanical helper (Haiku) | none used: the work was small enough to keep | 0 |

## PC steps with the market CLOSED (round 2, Saturday 21:00)
Pull this branch, restart the backend only. Have the playbook "R2 test" from round 1 (T-06 weekly 50 / 50 / 40, monthly 30 / 30 / 20) as the active Iron Condor playbook, one running MONTHLY trade and one running WEEKLY trade (both Iron Condors, plan accepted from "R2 test"). The contract list must be loaded (a market day fetched at least once).
1. Monthly trade: type stop 45 > Save > read on Positions, the builder and Plan watch: 45 everywhere. Weekly trade: the same, 45.
2. Monthly trade: change only the Target > Save: stop stays 30 on the answer, and 30 after closing and reopening, on Positions, builder and Plan watch. Weekly trade: stays 50.
3. Which row the live check used: open Plan watch for each trade, read the stop line: the monthly trade's stop line is the 30 % of its stored max loss (not 50 %); the weekly trade's the 50 %. In the worker log look for the line "adjustment check:" of the strategy; the stage row is in the `stops` of the state. (There is no new reply field; the stop figure on Plan watch is the one the check reads.)
4. Press "Reset to playbook" on each trade, confirm: the sheet shows "Put back to the playbook's values: ..." and "Switched on again: ..." (or "Nothing differed from the playbook, so nothing was put back."). Change T-02 first and switch T-05 off so you have something to see. The typed target, stop and time exit stay.
5. A trade whose expiry is 30 Mar 2027 (if you have one): the sheet shows no stop number and says why; a rupee stop saves.
6. Save a plan and, in the same moment, switch the PC network off or kill the backend request after the click (timeout); then reload: the plan is there complete (rules, exits where the screen shows them).
Report any step where the stop number differs between Positions, builder and Plan watch for the same trade.

New on-screen sentences (all pending owner read): "Put back to the playbook's values:", "Switched on again:", "Nothing differed from the playbook, so nothing was put back." (Lane O's; labels `reset_put_back*`).

SAFE TO CLOSE (head 7da2e173 on hotfix/plan-read-2-1127; the J2 hand-overs above stay open)
