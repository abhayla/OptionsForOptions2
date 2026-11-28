STATUS 19:35 | item 1: Fixed, not tested | items 2a-2d, 3: Fixed, not tested | extra (playbooks route): Fixed, not tested | next push: none (this is the one push, made only if the gate ends TOTAL PASS) | blocker: none

# Lane R2: plan reads use the row the save uses (hotfix/plan-read-1127)

Spec basis: ADR-330 (1) (the stop base and the stop the checks read), (5) (a base that cannot judge refuses), ADR-252 (the sheet's stop edit IS the T-06 value the live check reads), ADR-003 (decision-support wording).
Base: origin/hotfix/plan-save-1127 8b45807. Status words: nothing here is approved until it passes on the owner's PC.

## Bad news first
- NOT DONE (two hand-overs from the coordinator, arrived after the gate had started; a second gated push does not fit the 180-minute budget): (1) Lane O's `lane-o-item1-for-lane-r2.patch` (Reset names what it put back, T2-19). It needs a manual merge: it edits `_sheet`/`reset_plan` and calls `_kind_of`, which this branch deleted; it also edits `AdjustPlanSheet.vue`, `adjustPlan.js`, `plan-reset-p8.test.js`, `explanations.py`. (2) Lane J's cause (c): after a TIMED-OUT save the next read must return the stored plan complete (rules and exits); no test written yet. Next command for both: `git checkout hotfix/plan-read-1127 && git show origin/fix/alert-screens-1127:docs/design/next-batch-2026-11-26/lane-o-item1-for-lane-r2.patch > /tmp/o.patch && git apply --3way /tmp/o.patch`, then replace the patch's `_kind_of(tracked, money)` by `row.kind, ..., row.reason` as in this branch's `reset_plan`.
- The far-month rule is fixed only on the plan route. The live check and the worker read the same expiry through `adjustment_readers.expiry_kind_of`, which still answers "weekly" for a leg whose own month future is not listed. That is not mine to change (live check and worker belong to other lanes). With the market OPEN such a leg can show the weekly row. See "To file".
- Lane R's review item "read says weekly after a monthly save" was only visible when the saved stop was NOT typed: a typed percent stop writes BOTH rows (`set_max_loss_stop`), so the read-back of a typed stop was always the same number. The flip showed on a save that keeps the stop (target only, rupee stop, reset). The test uses that case.
- Some test files fail on my scratch database only (role allowlist pins: `test_migration_plan_stop_base`, `test_strategy_alert_style` post-allowlist, `test_ic_s08_s09_guidance_migration`, `test_playbook_store` x3, `test_migration_0031` downgrade): my scratch `ofo_app` role has broad grants, so tests that pin the real role fail. They do not touch the changed code. CI's database is the check.

## Core and proof (item 1)
Core: every read and write chooses the T-06 row through one function. Proof, before any fix: saved a plan with the market closed (no Kite session, scenario kind monthly), target only. The save answer showed stop 30 (monthly row). Then `GET plan` showed 50, `GET levels` passed kind "weekly", reset showed 50. 3 of 3 readers red (`tests_app/test_plan_read_1127.py`, `assert (Decimal('50') == Decimal('30'))`, `['weekly'] == ['monthly']`). After the fix all three are green.

## What changed (`backend/ofo_app/routes/adjustment_plan.py`)
| Item | Change | Test |
|---|---|---|
| 1 | `_kind_of` is deleted. `_known_kind(db, tracked, market)` is the only rule: the market's kind, else the stored catalogue by `expiry_kind_of`, else NOT KNOWN with a reason. `read_plan`, `read_levels`, `reset_plan` and the save reply all call it. With the kind not known the sheet shows no stop (percent figures, stop words) and a new field `stop_kind_reason` carries the sentence. A rupee stop keeps its own figures. | `test_read_plan_with_no_session_reads_back_the_saved_monthly_stop`, `test_read_levels_with_no_session_uses_the_saved_kind`, `test_reset_with_no_session_answers_the_monthly_row_of_the_playbook` |
| 2a | A leg expiring after the last listed future of its underlying (a far month with no future of its month) is NOT KNOWN, not weekly (`_stored_kind`). | `test_a_far_month_with_no_future_of_its_month_is_not_known_not_weekly`; `test_the_stored_kind_is_the_one_rule_over_the_stored_catalogue` extended |
| 2b | A percent stop with the kind not known is refused only when the two T-06 rows differ. With equal rows (and equal stop sentence) the kind cannot change the answer, so it saves. | `test_a_percent_stop_is_saved_with_the_kind_unknown_when_both_rows_are_equal` |
| 2c | A database error in the catalogue read is NOT KNOWN with its own reason (`plan_stop_kind_catalogue_unreadable`), the session is rolled back so later reads still answer, and a percent stop is refused. It never reads as weekly. | `test_a_catalogue_database_error_is_not_known_with_its_own_reason`, `test_a_real_database_error_in_the_catalogue_read_leaves_the_session_usable` (a real `SELECT 1/0`; without the rollback it fails: checked) |
| 2d | The monthly case runs on a stored FUTURE row (catalogue, no scenario), not only the scenario stand-in. | `test_a_stored_future_row_on_the_leg_day_reads_back_the_monthly_stop` |
| 3 | Own server-built sentence for the percent refusal: "The stop could not be saved: whether this trade expires weekly or monthly could not be read." Next: "Try again when prices update, or save the stop as a rupee amount." (`plan_save_percent_stop_not_read`, ERR SV 527). Pending owner read. | `test_a_percent_stop_with_no_session_and_no_stored_kind_is_refused_and_writes_nothing` (exact text) |

New wording, all pending owner read (pins added with `reviewed: pending owner read`): `plan_save_percent_stop_not_read`; "Stop not shown: whether this trade expires weekly or monthly is not known right now"; "Stop not shown: the contract list could not be read, so the expiry type is not known".

## Opus review of item 1 (stop path)
Why Opus: stop path; a wrong row is a stop that never fires. One independent review (verdict REVISE), round 2 used:
| Finding | Result |
|---|---|
| MAJOR far-month rule lives only on the plan route | Not fixed here (live check, worker: other lanes). Filed below. |
| MAJOR a real PostgreSQL error leaves an aborted transaction | Fixed (rollback) with a real-error test. |
| MINOR `_rows_alike` ignored a rupee stop making T-06 inactive | Fixed + test. |
| MINOR levels dropped the rupee-stop-above-max-loss warning when kind unknown | Fixed + test. |
| MINOR reason hidden when a picked playbook's rows agree but the saved plan's do not | Fixed + test. |
Passed attacks (reviewer): equal first stages with different later ones; typed value equal to the shown stop writes nothing; "50" vs "50.0" fails closed; T-16 rows differ; money Decimal, no float, no paper-only branch.

## Extra item from the coordinator: `routes/playbooks.py`
Confirmed with a test, then fixed. The playbook test route (`POST /api/playbooks/test`) read the strategy list and the tracked legs on the request's session and then waited on market reads with that transaction open: same pattern as Lane R's plan-save fix (D-36 (c)). Now the legs are read one after another, `release_connection` is called, then the market reads run together. Test `test_no_database_connection_is_held_across_the_market_read` (first market read sees 0 idle-in-transaction sessions; before the fix it saw 1; checked by removing the release). Not fixed: after the first read the spot and margin seams of the other strategies use the request's session again while another strategy waits on the market (one connection, not a leak); see "To file".

## Paper-only paths found (ADR-330 (58))
- `frontend/src/components/strategy/PlanEntry.vue:65`: the `exits` prop is documented as the armed/fired exits from `GET /paper/strategies/{id}/triggers`; the loader is `frontend/src/lib/paperTriggers.js:5` (`triggersPath`), a paper route. Verified by reading; not changed (not mine). A real-mode trade has no equivalent read in this component.
- In my files: none. The plan routes and readers have no paper-only branch.

## To file as deferred issues (not filed by me)
1. `adjustment_readers.expiry_kind_of` (line 838) answers "weekly" for a far-month leg whose own future is not listed; the live check (`adjustment_check.py:396`) and background (`background.py:~397`) trust it. Repro: futures {24 Nov, 29 Dec, 26 Jan}, leg 30 Mar 2027 -> "weekly". Should answer "not known" and the check fail closed. Stop path.
2. `adjustment_check.py:299` reads `position.expiry_kind or "weekly"`, and the position's kind is always "" (`adjustment_readers.py:161/171/290`), so those T-09 inputs always use the weekly row.
3. `routes/playbooks.py` test route: spot and margin seams reopen a transaction on the request session during other strategies' market waits.
4. `read_levels` now loads the catalogue on every call when the market is closed (one extra read); cache it if it shows.
5. `AdjustPlanSheet.vue` does not yet show the new `stop_kind_reason` sentence (the sheet shows an empty stop box with no explanation) until the lane that owns the sheet adds it.

## Tasks, models, minutes
| Task | Model | Minutes |
|---|---|---|
| Read, failing test, fix items 1-3, playbooks fix, tests, RESULTS | Sonnet (this session) | about 125 |
| Independent review of item 1 | Opus (reviewer agent) | 6 |

## PC steps with the market CLOSED (round 1, about 01:00)
Pull this branch, restart the backend only. Set up once: Settings > Adjustments > the Iron Condor playbook > make a copy named "R2 test" with T-06 weekly 50 / 50 / 40 and monthly 30 / 30 / 20 (the system playbook has equal rows, which would hide the difference), make it your active Iron Condor playbook. Have one running MONTHLY trade and one running WEEKLY trade, both Iron Condors, with the plan accepted from "R2 test".
Expected values (stop box on the plan sheet, first stage): monthly trade 30, weekly trade 50.
1. Positions > the monthly trade > Adjustment plan: stop shows 30. Open the builder for it and Plan watch: same 30 (read, no save).
2. Weekly trade, same three places: 50.
3. Monthly trade: change only the Target to 60, Save. Expect the saved plan to still show stop 30 on the answer, then close and reopen the sheet, Positions, builder and Plan watch: still 30 (before the fix the reopened sheet said 50).
4. Weekly trade: same Target-only save: stop stays 50 everywhere.
5. Monthly trade: type stop 45 > Save: expect 45 everywhere (a typed stop is written to both rows). Press Reset to playbook: expect 30 on the answer and after reopening.
6. Weekly trade: same: type 45, Save: 45; Reset: 50.
7. If the contract list is not loaded (no market day fetched): percent stop Save is refused with "The stop could not be saved: whether this trade expires weekly or monthly could not be read." and the stop box is blank with no number; a rupee stop Save works. Note it and the deployed commit if you see a stop number instead.
8. Playbooks > Test on a type with several trades: the page answers as before (no visible change expected).
Report any step where the stop number differs between Positions, builder and Plan watch for the same trade.
