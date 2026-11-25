# Next batch plan: ADR-330 and the screen-check bugs (written 25 Nov 2026 night, for 26 Nov)

Documents only. No product code and no `spec/` edit is made by this file. A fresh session builds from it without asking
anything; every genuine owner question is in section 6 with its recommendation and what is built meanwhile.

Standing direction: this plan belongs to **step 4 (the tracking journey), item 10 "triage and fix the defects that make
suggestions wrong"** for the plan, alert and stop items, and to **clean-up D-08 (one true status record) / step 4 item 9
(hide what is not real)** for the screen bugs. It is also covered by one question (Q1): the iron-condor freeze and the
owner's ADR-330 words (the change log of `docs/process/standing-direction.md` ends on 2026-11-12; I found no later
line).

## 0. How this was verified (read before trusting a line number)

| Ref | What I read | Used for |
|---|---|---|
| `fix/ic-live-test-1123` at `e01f747` (this worktree) | `backend/`, `frontend/src/`, `spec/decisions/ADR-330.md` | "Today" facts, tagged **[fix]** |
| `origin/refactor/modular-doors` at `a99730b8` | `PLAN-phases-3-8.md`, `PLAN.md`, `RESULTS.md`, `evidence/combined-findings-2026-11-25.md`, `backend/ofo_app/market_read.py`, `may_act.py`, `frontend/src/lib/priceState.js`, `legDoor.js` | Doors that exist today, tagged **[refactor]** |
| `origin/docs/screen-checks-2026-11-25` | `docs/process/screen-checks-2026-11-25.md` (S-01 to S-28, OD-1 to OD-5) | The findings |

Doors on the refactor branch **today** (code read): `read_market` (`market_read.py:90`), `may_act` (`may_act.py:88`,
actions `place` / `exit` / `set_trigger`, `:41`), `priceState` / `usePriceFreshness` (`priceState.js:29,:37`), the leg
rule `admitLegs` (`legDoor.js:19`). **Not yet code** (planned only, `PLAN-phases-3-8.md` sections 5.3 and 5.4):
`strategy_money_view` (Phase 3, `be/strategy_money.py`), `exit_strategy` / `live_exit_prices` (Phase 4, `be/paper_exit.py`,
`ofo/tracking/closing.py`), `usePaperExit` + `ExitButton` (Phase 4), `useLegDoor` (Phase 5, Lane B). Anything below that
needs one of those says **WAITS (Phase N)**. Line numbers of the refactor branch are those of `a99730b8`; lines of
**[fix]** are those of `e01f747`. Unverified claims are marked **Unverified** with the first command that settles them. Verification pass of 25 Nov: the first
commands were run against `e01f747`; what they settled reads **Verified [fix]** with file:line, what code cannot settle reads
**Still open** with the exact access that settles it.

Two things the refactor plan decided that this plan changes (the later owner words win):
1. `PLAN-phases-3-8.md` section 2.2 and Phase 6 say "B7 `raise_alert` not built; guard G4 pins one caller per writer". The
   owner's standing instruction in ADR-330 ("every actionable alert ... ONE shared module ... no trigger writes its own
   alert code") reverses that. Item P1 builds the module; guard G4 (`tests/test_alert_writers_one_caller.py`, Phase 8)
   becomes the guard of item P1 (its allowed home changes from three writers to the one module).
2. The refactor bounds say "no auto-exit from plan targets" and "exit is now / market only". ADR-330 (5)(b) agrees: plan
   levels raise alerts, nothing exits by itself. Only the Stops-panel exits (index conditional exit, leg stop) exit by
   themselves, as today.

## 1. Item list at a glance

Order inside each lane is the build order. Size S under half a day, M about a day, L multi-day. "Wave 1" = buildable from
the fix-branch head today; "Wave 2" = after the owner lets `refactor/modular-doors` merge (lanes then `git merge
origin/refactor/modular-doors`, never rebase).

| Id | Item | Source | Lane | Wave | Size | Risk |
|---|---|---|---|---|---|---|
| P1 | The ONE actionable-alert module + the one info pop-up + guards (bell = unanswered) | ADR-330 (3), (4), standing instruction; S-16, D-29 | P | 1 (alert writes in `paper_monitor` are wave 2) | L | Tier A: migration, order-adjacent |
| P2 | Only a strategy's own plan applies (no playbook fallback) | ADR-330 (11), OD-3 | P | 1 | S | Wrong if existing strategies have no plan |
| P3 | Stop amounts fixed at entry | ADR-330 (1), S-21 | P | 1 | M | Tier A: migration, money |
| P4 | Rupee plan levels, both figures shown (+ hints S-12) | ADR-330 (5), S-10, S-12, D-34 | P | 1 | M | Tier A: money |
| P5 | Plan time exit on any day | ADR-330 (7), S-13 | P | 1 | M | Tier B |
| P6 | Max-loss line on a leg stop (before save and in the alert) | ADR-330 (6), S-22 | P | 1 (alert line wave 2) | M | Tier B (reads engine only) |
| P7 | Plan after a side exits: not-applicable lines and the add-legs / confirm-new-shape question | ADR-330 (2), S-27 | P | 1 backend; page part wave 2 | L | Tier B |
| P8 | Playbooks and plans: several standard playbooks per type, two levels, change or switch off but never add, Reset, only the type's playbooks (+ S-11) | ADR-330 (9), S-17, S-11 | P | 1 | L | Tier A: migration |
| P9 | Stand-alone condition checks calling the one exit function | ADR-330 (12), OD-2 | P | 2 (needs `exit_strategy`, Phase 4) | M | Tier A (exit path) |
| P10 | The live Plan watch box | ADR-330 (13), OD-5 | P | 1 server, 2 screen | L | Tier B |
| P11 | S-15 server line: the Paper totals say what they include | S-15 | P | 1 | S | Tier B |
| P12 | S-07: the word "Strategies" in the top menu opens the menu | S-07 | P | 1 | S | Tier C |
| Q1 | Bulk delete on My Strategies / Completed (+ S-04 control jump, S-03 wording, S-05 loading, S-02 cause) | ADR-330 (8), S-01, S-04, S-03, S-05, S-02 | Q | 2 (`MyStrategiesPage.vue` is edited by refactor Phase 6 F8) | M | Tier B |
| Q2 | One Positions list for real and paper (+ S-28, S-23, S-19, S-26, S-15 screen half) | ADR-330 (10), OD-1, S-28, S-23, S-19, S-26, S-15 | Q | 2 (`PaperStrategies.vue` is edited by Phase 4) | L | Tier B |
| Q3 | Overview link carries the id; the Live card opens the strategy | S-18, S-14 | Q | 1 | S | Tier B |
| Q4 | Plan summary: breakevens say their basis; chain picker prices; Orderbook columns | S-06, S-09, S-25 | Q | 1 | S to M | Tier B |

Findings S-02 to S-28 NOT in this table, and why (every id is placed once):

| Id | Covered by |
|---|---|
| S-08 (unsaved builder legs lost) | `ADR-329`, refactor Phase 5 (Lane B): leave question and chain-trip hold |
| S-20 (leg-stop reason "index not available") | Refactor Phase 1, DONE (`fce27095`, `58bd51d9`, `3b8ae9b7`) |
| S-24 (leg stop saved past the live price) | Merged into D-01; refactor Phase 1 `check_trigger_levels` / ADR-327, DONE. The retest on a quiet leg stays on the owner's list (`PLAN-phases-3-8.md` section 8) |
| S-16 (alert lapsed in 3 minutes) | ADR-330 (3): item P1 |
| S-21, S-10, S-12, S-13, S-22, S-27, S-17, S-11, S-01 | ADR-330 items P3, P4, P5, P6, P7, P8, Q1 |
| S-03, S-04, S-05, S-02 | Section 3 below (bug list), built inside Q1 because the same files |
| S-15 | P11 (server) and Q2 (screen), because ADR-330 (10) rewrites the same totals |

## 2. The shared design: one alert module, one pop-up (item P1 first)

**Spec basis.** ADR-330 (3): "(a) ACTIONABLE: the user's plan says he should act (the plan's loss stop crossed, its profit
target reached, an adjustment rule fired). Such an alert does not close, lapse or leave the Active list until the user
himself acknowledges it and takes his call: exit the position, or continue with the position ... The alert only informs
and asks: it never exits by itself (decision support, ADR-003)". (3b): "INFORMATIONAL: nothing for the user to do ... a
short pop-up that disappears by itself and is kept only in History". (4): "the bell counts the actionable alerts of
point (3) that the user has not yet answered, and that number equals the number of rows in the Active list".
Standing instruction: "every 'actionable alert' above is raised through ONE shared module, called with the kind of
condition that was met and its facts; no trigger writes its own alert code."

### P1 Verified facts today [fix]

- **Four writers, none shared.** (1) a fired Stops-panel exit: `paper_monitor.py:238` `triggers.add_alert` inside
  `_fire` (`paper_monitor.py:205-246`) into table `paper_alerts` (`paper_trigger_store.py:50` `_ALERT`, `:149`
  `add_alert`). (2) plan and adjustment rules: `background.py:809` `playbook_store.open_suggestion`
  (`playbook_store.py:741`) into `adjustment_suggestions`, through `Gate.apply` (`background.py:783-818`). (3) held crossings
  `playbook_store.record_held` (`:938`, called `background.py:803`). (4) worker silence `notifier.notify`
  (`notifier.py:77`, one caller `worker_watch.py:153`).
- **The lapse that caused S-16.** `alert_gate._refresh` (`alert_gate.py:196-221`) emits `Lapsed` when "a close clears its
  line by the re-arm band" (ADR-237 (4)); `background.py:793-794` then calls `_lapse_open_of(... LAPSE_CONDITION_STOPPED)`
  (`background.py:713`) which calls `playbook_store.lapse` (`playbook_store.py:834`). Real case 25 Nov: fired 11:02:20,
  lapsed 11:05:01 (value fell back past the band), the loss then grew. Other lapse reasons today:
  `strategy_closed`, `superseded_by_worse` (`background.py:808`), `not_monitored`, `position_changed`
  (`playbook_store.lapse_changed:879`), `contract_expired` (`:870`) (`playbook_store.py:56-67`).
- **Bell and list.** `bellCount = paperAlerts.unread + openRecords.list.length` (`paperAlerts.js:84`);
  `attentionItems` (`paperAlerts.js:88`) = open records + unread stops; opening Alerts > Active calls
  `markPaperAlertsRead()` on mount (`AlertsPage.vue:35`), so stops leave the count by merely looking. Real case 25 Nov:
  bell 1, Active 4 rows (D-29).
- **Pop-up.** One consumer: `AppHeader.vue:42` `announce` calls `showToast(... 'info')`; `useToast.js:32` "never expires".
  ADR-330 (3b) wants it to disappear by itself.
- **Delete hides alerts.** ADR-293 (3): a deleted paper strategy's alerts leave the bell; the module must keep that (the
  readers join `strategies.deleted_at IS NULL`, `paper_trigger_store.py:55-58`).

### P1 The module (one new module, reuse the stores)

- New `backend/ofo/alerts.py` (stdlib only): `AlertKind` table, kind -> (allowed answers, wording template id).
  Kinds: `plan_loss_stop`, `plan_profit_target`, `plan_rupee_loss`, `plan_rupee_profit`, `plan_time_exit`,
  `adjustment_rule`, `side_closed` (answers `add_legs`, `confirm_new_shape`); every other kind answers `exit` or `continue`.
  Informational kinds: `stop_fired`, `settled`, `orders_placed`, `stop_saved`.
- New `backend/ofo_app/actionable_alerts.py`, the ONLY writer: `raise_actionable(conn, user_ref, strategy_id, kind, facts)`
  (one open row per (strategy, rule): a second call for the same rule updates the facts and keeps `fired_at`),
  `note_condition(conn, ..., alert_id, still_true, at)` (sets `no_longer_true_since`, never closes),
  `answer(conn, user_ref, alert_id, answer, at)`, `unanswered(conn, user_ref)` (the Active list), `unanswered_count`
  (= `len(unanswered)`, one SQL, so the bell cannot differ), `inform(conn, user_ref, strategy_id, kind, text)` (History row,
  never counted). Storage reuses `adjustment_suggestions` (it already holds the open record, `value`, `threshold`, timeline,
  unique open row per rule `playbook_store.py:324`); a migration adds `kind`, `answer`, `answered_at`,
  `no_longer_true_since`. No second store.
- **Exit answer**: the Active row's "Exit" button opens the usual paper exit confirmation (shared `ExitButton` /
  `usePaperExit`, refactor Phase 4); "Continue" stores the answer. Neither exits by itself. **WAITS (Phase 4)** for the
  exit button; until then "Exit" links to the builder page of that strategy (`?strategy=<id>`).
- **Which lapses remain.** `condition_stopped` and `superseded_by_worse` no longer close an actionable alert (the first sets
  "no longer true since HH:MM", the second updates the open row's facts). `strategy_closed`, `contract_expired`,
  `position_changed`, `not_monitored` still end the question because the position the question is about is gone; they
  store `answer = 'closed_by_system'` with the reason and show in History (reading, see Q2b).
- Frontend: `lib/paperAlerts.js` `bellCount` = server count of unanswered (no addition of two sources); AlertsPage Active
  lists exactly `unanswered`, no mark-read on mount; each row shows "Fired at HH:MM", "no longer true since HH:MM" when set,
  and two buttons from the kind's answers; History shows the answer and its time. `lib/infoPopup.js` = the one pop-up
  (auto-dismiss, constant `INFO_POPUP_MS = 6000` in one home); `useToast.js` keeps the list but only `infoPopup.js` and
  `ToastHost.vue` may import it.
- **Guards (structural, kit C3).** `tests/test_actionable_alert_one_module.py` (`repo_scan`, AST): a call of
  `open_suggestion`, `record_held`, `add_alert`, `notify`, or an `INSERT INTO ... adjustment_suggestions|paper_alerts`
  outside `actionable_alerts.py` fails with file, line and the module name; exemptions keyed (file, function) with a
  category, stale exemption fails. `frontend/tests/one-popup-module.test.js`: `showToast(`/`useToast` only in `infoPopup.js`
  and `ToastHost.vue`; no other component renders its own `role="alert"` pop-up list. Both with mutation samples
  (in-memory bad file -> exactly one problem; allowed home -> none). This **replaces** refactor guard G4.

### P1 Tests first (exact assertions; DB test via `db_run.py`, one file only)

`tests_app/test_actionable_alerts.py`:
1. Core, on the REAL S-16 sequence: raise `plan_loss_stop` for strategy S at 11:02:20 value 15.5750 rule 15.4000; call
   `note_condition(still_true=False, at=11:05:01)`; then call `unanswered`: exactly 1 row, `fired_at` 11:02:20,
   `no_longer_true_since` 11:05:01, outcome still open. Today this fails (the row lapses).
2. Answer states of `answer`: stated (`exit` / `continue`) -> row leaves `unanswered`, History row carries answer and time
   (assert `answered_at` IST); absent (no answer given) -> row stays; not found (id of another user, or hidden strategy) ->
   `SUGGESTION_NOT_FOUND`, nothing written; failed (DB error inside the savepoint) -> row unchanged, error raised not
   swallowed; empty (`answer=""`) and ambiguous (`"exit"` for kind `side_closed`, which allows `add_legs` /
   `confirm_new_shape` only) -> `AlertAnswerRefused`, nothing written; second answer on an answered row -> refused
   (`SUGGESTION_NOT_OPEN`, as `_close` does today, `playbook_store.py:779`).
3. Bell = Active: with 0, 1 and 4 unanswered rows `unanswered_count == len(unanswered)`; with 1 unanswered and 3 answered
   the count is 1 (the D-29 case 25 Nov inverted: bell must equal the list).
4. Informational: `inform(...)` adds a History row and changes `unanswered_count` by 0.
5. One open row per (strategy, rule): a second `raise_actionable` for the same rule returns the same id; a worse value
   updates `value`, keeps `fired_at`, adds a timeline entry.
6. Deleted strategy: after ADR-293 delete, its alert is in neither `unanswered` nor the count; Undo brings it back.
7. Never exits: after `raise_actionable` for `plan_loss_stop`, `paper_orders` count for the strategy is unchanged.
`frontend/tests/alerts-actionable.test.js`: bell number printed equals the server's `unanswered` and the row count of the
Active list; opening Active posts nothing to `/paper/alerts/read`; row with `no_longer_true_since` shows both times; Exit
button present, Continue posts the answer. Existing tests changed in the tests-first commit with the reason in the message:
`frontend/tests/alerts-bell-matches-list.test.js`, `paper-alerts.test.js`, `header-bell-open-records.test.js`,
`alerts-one-record.test.js` (they pin "read stops leave the count" and "bell = two sources").

### P1 Code steps, in order

1. Migration (Tier A, its own commit, own DB test `tests_app/test_migration_actionable_alerts.py`): four columns on
   `adjustment_suggestions`; the guard that forbids edits there (0031) is extended for the new columns only.
2. `ofo/alerts.py` kinds table + wording templates in the catalogue (`ofo/errors/explanations.py`, with pins).
3. `actionable_alerts.py` + `tests_app/test_actionable_alerts.py` green.
4. `background.py` `Gate.apply` (`:783-818`): call `actionable_alerts` instead of `playbook_store.open_suggestion`; the
   `Lapsed` event calls `note_condition`, not `lapse`. `playbook_store.py` keeps the SQL helpers, the module imports them.
5. Frontend: `paperAlerts.js`, `AlertsPage.vue`, `AppHeader.vue` (bell), `infoPopup.js`, `useToast.js`, `ToastHost.vue`.
6. Guards. 7. **Wave 2:** `paper_monitor.py:238` `add_alert` -> `inform(kind='stop_fired')` (and the S-22 line, item P6);
   `notifier.notify` stays the worker-silence channel, wrapped by `inform` (it is not an alert of a strategy).

**Depends on refactor:** Exit button (Phase 4), `paper_monitor.py` edit (Phase 4 owns that file), guard G4 replaced (Phase 8).
**Size L, risk Tier A.** **Owner question:** Q2 (is a fired Stops-panel exit informational) and Q2b (strategy closes first).

## 3. Lane P, the ADR-330 items after the module

Common to the alert-raising items (P4, P5, P7, P9): each is a check that ends in `actionable_alerts.raise_actionable` (never its own alert
code) and reads money from the one engine (ADR-008).

### P2 Only a strategy's own plan applies (OD-3)

**Spec basis.** ADR-330 (11): "A strategy with no plan gets no adjustment suggestions and no target or stop alerts, and
shows 'No plan: nothing is watched for this strategy'. Its Stops-panel index exits and leg stops are separate and keep
working. SPEC CHANGE to REQ-158 ... and REQ-161 ('No plan saved yet: default rules apply' ends)."
**Verified [fix].** `adjustment_check.resolve` (`adjustment_check.py:218-229`): plan, else `playbook_store.active_for`
(`:226-229`), else system default. A `Resolved("none", ...)` branch already exists (`:223-224`, only for `stype is None`) and `settings_in_force.stops_of`
already answers `NO_PLAYBOOK` for it (`settings_in_force.py:373-374`). Five callers: `adjustment_readers.py:288`,
`paper_limit.py:43` (the adjustment-limit count of a manual order), `background.py:1923`, `routes/adjustment_check.py:460`,
`routes/adjustment_history.py:167`. Old screen text: REQ-161 line 45, ADR-295 line 8, ADR-214 line 87.
**Reuse:** the existing `none` branch. **New:** nothing. **Code:** delete `:226-229` so a missing plan returns `none`;
`background.py` skips a strategy whose `resolved.source == "none"` (nothing watched); `paper_limit.py:43` with `body is None`
applies no limit (reading, Q7); screen text `NO_PLAN_TEXT = "No plan: nothing is watched for this strategy"` in the
catalogue, shown by `PlanEntry.vue` / tracking panel (replaces the "No plan saved yet" card).
**Tests first:** `tests_app/test_resolve_own_plan_only.py`: strategy with plan -> `source == "plan"`; no plan but an active
playbook of the type -> `none` (red today: returns `active`); no plan and no type (`stype is None`) -> `none`; strategy
not found / another user's -> `not_found` raised as today; plan row present but body unreadable -> refused, not "none"
(fail closed, never "nothing watched" by accident); `test_background` with a plan-less strategy: zero records opened and
`stops` not checked, while an armed index exit still fires (`test_paper_monitor.py`). Frontend: `PlanEntry` shows the exact
sentence for "no plan", never the old one.
**Risk:** every strategy that has no plan today (the owner's 100-odd test strategies) goes silent on deploy; that is the
owner's decision (ADR-330 (11), "CONFIRMED 11:50"), but the release note must say it. **Size S.**

### P3 Stop amounts fixed at entry (S-21)

**Spec basis.** ADR-330 (1): "the rupee amounts of a plan's stop line ... are worked out ONCE, from the trade as entered,
and stay fixed. They change only when the user edits the plan. Closing a side or a leg does not move them." Real case 25 Nov:
"Rs 400.40" at 10:32, "Rs 756.76" at 12:55, "2 x credit" Rs 7,800 -> Rs 3,172.
**Verified [fix].** The base is recomputed from the LIVE legs at every check: `adjustment_check.state_of` computes `gross`
from `price_after(position.legs ...)` (`:375-378`) and `credit` from `net_credit_so_far` over the current legs
(`:393-394`), then `sif.stops_of(resolved, MoneyInputs(gross.max_loss, credit, margin), ...)` (`:395`). The plan sheet reads
the same through `settings_in_force.money_inputs` (`settings_in_force.py:212-222`). `entry_facts` (`0039`) holds only
`entry_spot` / IV, no money. A plan row is written by `playbook_store.accept_plan` (`:664-688`, callers
`routes/adjustment_plan.py:484,:575`).
**One home:** new `StopBase(max_loss, credit, taken_at, source)` stored on the plan row (new column `stop_base` JSONB on
`strategy_adjustment_plans`, one migration); `accept_plan` computes it once from the strategy's ENTRY orders (kind not
`exit` / `stop` / `settle`) through the same `price_after` engine call, never from the open legs; `settings_in_force.stops_of`
callers read `StopBase` only (both `state_of` and `money_inputs`). A plan edit (`PUT`) recomputes it.
**Tests first** (`tests_app/test_stop_base_fixed.py`, DB): the 25 Nov strategy rebuilt from its stored orders: base max
loss 2,600, 15.4 % = Rs 400.40; close the call side (two exit orders) -> `stops_of` still returns Rs 400.40 and credit line
Rs 7,800 (red today: 756.76 / 3,172.00); edit the plan -> base recomputed from entry orders, line changes; answer states:
base stored (stated), plan with no stored base (a plan saved before this change: absent -> computed once, stored with
`source='backfill'`, assertion that a second read does not recompute), entry orders unreadable (failed -> stop line says
"not checked", never a number from the live legs), strategy with no entry orders (empty -> "not checked"), unlimited max
loss (ambiguous: `UNLIMITED` stored as the sentinel, % line answers not computable, credit line still works), plan not
found -> `none` (P2). Assert no float: the stored text is `format(Decimal, "f")`.
**Code:** migration; `StopBase` in `settings_in_force.py`; `accept_plan` writes it; `state_of` and `money_inputs` read it;
remove the `price_after` call used only for stops (keep the one the approach builder needs). **Depends on refactor:** none
(files untouched by Phases 3 to 8). **Size M, risk Tier A** (migration, money).
**Owner question:** Q4 (does an adjustment move the base).

### P4 Rupee plan levels (S-10, S-12)

**Spec basis.** ADR-330 (5): "(a) a plan's profit target and loss stop can be typed either in rupees or in percent, and
the plan shows both figures. (b) A rupee level behaves exactly like every other plan level when it is hit: it raises an
actionable alert of point (3) and nothing exits by itself." Not chosen: percent only; auto-exit switch.
**Verified [fix].** The sheet has `target` / `stop` as percent only (`AdjustPlanSheet.vue:25-37`, `adjustPlan.js:61-69`
`saveBody`, server `routes/adjustment_plan.py:82-96`); the guards are `profit_target_pct_of_max_profit`
(`adjustment_check.py:189-213` `with_plan_target`) and the T-06 stop edited by `settings_in_force.set_max_loss_stop`
(`:385-406`). Hints after typing stay "50 %" (S-12, `stopWords` / `targetWords` come from the server at load only,
`adjustPlan.js:20-21`). The plan shows a rupee figure for the stop only. The basis of the percent target is before
charges (screen note 25 Nov). T-07 is the target trigger (`playbook_eval.py:593`).
**Design.** Two new guard keys `profit_target_rupees`, `loss_stop_rupees` (text decimals, `check_body` extended); two new
pure checks in `ofo/adjustment/` (`rupee_level.py`: `pnl_at_or_beyond(level, pnl, kind)` -> met / not met / not computable)
raising kinds `plan_rupee_profit`, `plan_rupee_loss` through the module. The sheet gets a rupee box beside each percent box;
typing one fills the other from the SERVER (`GET .../adjustment-plan/levels?target_rupees=...` returns both figures; the
browser computes nothing, ADR-008); the plan block shows both.
**Tests first:** `tests/test_rupee_level.py` (pure): profit exactly at level -> met; one paisa below -> not met; negative
pnl for a loss level; pnl `None` -> not computable (never "not met"); level `""` -> no check; level `0` or negative -> refused;
`Decimal("NaN")` refused; no float. `tests_app/test_plan_rupee_levels.py`: 1,000 rupee target on a 3,900 max-profit trade
shows 25.64 % and Rs 1,000 together; a percent edit recomputes the rupee figure; saving both with different values ->
refused naming the field (ambiguous: one source of truth, the last edited box wins and the other is derived, assert that);
rupee level hit -> `raise_actionable(kind=plan_rupee_loss)` and `paper_orders` count unchanged. Frontend: typed 25.7 and
15.4 -> hints read the typed values with their rupee amounts (S-12), server-supplied, no browser arithmetic (assert the
network call, not a computed string).
**Depends on refactor:** none for the backend; `AdjustPlanSheet.vue` is not in a refactor row. **Size M, Tier A** (money).
**Owner question:** Q3 (before or after charges; whole trade or per lot).

### P5 Plan time exit on any day (S-13)

**Spec basis.** ADR-330 (7): "a plan's time exit can be set for any trading day and time, not only expiry day. At that time
it raises an actionable alert of point (3) ... nothing exits by itself." SPEC CHANGE to ADR-310 (2) ("the time exit acts on
expiry day only").
**Verified [fix].** `_t10b` (`playbook_eval.py:611-617`) raises `_Missing(waits_expiry_day)` unless `is_expiry_day(today,
expiry)`; the plan field is `guards["time_exit"]` as "HH:MM" (`routes/adjustment_plan.py:82,:291-294`); the sheet label says
"on expiry day" (`AdjustPlanSheet.vue:36`); `adjustment_check.py:282-315` feeds the clock (IST `hhmm`).
**Design.** `time_exit` becomes `{at: "HH:MM", on: "expiry" | "YYYY-MM-DD"}` (an old plain "HH:MM" reads as `on: expiry`,
no data change); `_t10b` compares today's date and the clock; the check raises `plan_time_exit`. New pure function
`time_exit_due(today, now_hhmm, on, at, trading_days)`; trading-day check uses the one calendar (`may_act.market_open`'s
calendar, **[refactor]** `may_act.py:68`; Wave 1 uses `routes.outcome.market_state` as today).
**Tests first:** `tests/test_time_exit_any_day.py`: `on` a date, before the time -> not met; at the time -> met; after, same day ->
met (stays met until answered); next day after the date passed -> not met and the alert (if unanswered) stays (P1);
`on` a holiday or Saturday -> refused at save naming the field; `on` earlier than today -> refused; `on` after the last
expiry of the legs -> refused; `on: expiry` unchanged (existing `test_playbook_eval` T-10b cases pass unmodified); the real
case: trade opened 25 Nov, expiry 1 Dec, time exit "15:15 today" -> alert at 15:15 on 25 Nov. Frontend: label reads
"Time exit", date box defaults to blank = expiry day.
**Depends on refactor:** none. **Size M, Tier B.** **Owner question:** Q9 (single date or every day).

### P6 Max-loss line on a leg stop (S-22)

**Spec basis.** ADR-330 (6): "the Stops panel shows, before he saves, what the trade becomes if that stop fires: 'If this
stop fires, max loss becomes Rs X (now Rs Y)', from the one engine (ADR-008). The same line is in the alert when the stop
fires. It informs only and never blocks the save." Real case 25 Nov: -2,860 -> -12,005.51 with no warning.
**Verified [fix].** The engine already answers this for exits: `engine/extremes.py:144` `exit_risk(book, basket, terms,
priced)`, the wording `paper_exit_widens_loss` (`explanations.py:1927`), the route `GET /paper/strategies/{id}/exit-risk`
(`routes/paper.py:1411-1450`, used by `PaperConfirmDialog.vue:131`). The Stops panel leg-stop save is `PaperStops.vue:104-112`
(`POST` kind `leg_stop`). The fire path builds its alert body in `paper_monitor.py:237-240`.
**Reuse:** `exit_risk` and the template; **new:** one route `GET /paper/strategies/{id}/leg-stop-risk?contract_id=&level=`
that builds a one-leg basket priced AT THE STOP LEVEL (a given price, not a live read) and calls the same
`_exit_warning`; the same function is called by `_fire` for the alert body (wave 2).
**Tests first:** `tests_app/test_leg_stop_risk.py`: the 25 Nov book (short 26000 CE, long 26100 CE, put spread): stop on the
short 26000 CE -> text "If this stop fires, max loss becomes Rs 12,005.51 (now Rs 2,860.00)"; stop on the long wing -> no
widening line (answer `no`); engine cannot price (a leg without a price) -> `cannot_tell`, panel shows no figure, save
still allowed (never blocks); strategy not found / another user's -> 404; contract not open -> refused; level not a multiple
of 0.05 -> same refusal as the save; unlimited result -> "no fixed maximum" wording (the screen note says "No fixed maximum").
Frontend: line appears before Save and the Save button stays enabled in every state; an unreadable answer shows nothing
(never the old figure). Fire path (wave 2): alert body contains the same line; `test_paper_monitor.py` keeps passing.
**Depends on refactor:** the alert line edits `paper_monitor.py` (Phase 4 owns it) -> WAITS (Phase 4); the route and panel line
do not. **Size M, Tier B.**

### P7 The plan after one side exits (S-27)

**Spec basis.** ADR-330 (2): "(a) The plan stays the one set at entry and only the rules that still fit keep running: a rule
for the closed side reads 'Not applicable: the <call or put> side is closed' ... (b) When a side closes, the user is told so
and asked whether he wants to add new positions on the closed side. If yes, the app takes him to add the legs ... If no, he
is told that the strategy will then change from its entry shape to the shape that remains (iron condor to bull put spread
when the call side closed; bear call spread when the put side closed) and asked to confirm. If he confirms, the strategy is
shown as the new shape from then on; the plan of (a) continues. If he does not confirm, he is asked again to add the legs
... Until he answers, the trade keeps its entry shape name with the notice showing. New legs are paper orders ... nothing is
added without the user."
**Verified [fix].** No side-closed state exists; open records for rules lapse as `position_changed`
(`playbook_store.lapse_changed:879`, `#685`). The plan keeps `strategy_type` forever (`accept_plan` refuses a type change,
`playbook_store.py:674-678`, guard OF031). The shape name comes from `ofo/strategy/matching.py` (the builder showed "Bull Put
Spread"). Evaluator reads only open legs (`state.shorts`, `playbook_eval.py:519-521`, `_t01 :547`), so the remaining side's
rules already work. **Verified [fix] (side-specific ids, read 25 Nov):** triggers are side-blind: they read only the open legs
and each short-based one (T-01 `_t01 :547`, T-01b `:560`, T-03 `:579`, T-09 `:607`) measures the remaining shorts; with no
short at all `_shorts` raises `_Missing(no_short_leg)` (`playbook_eval.py:518-521`). T-05 (`:722-731`) is side-specific by
nature (larger side value / smaller side value over CE / PE; with one side it reads `side_value_not_positive`, `:728-730`).
T-02 and T-07 read only P&L (`:565-567`, `:593-595`). The approaches already refuse by shape: `_condor()` returns None unless
exactly 4 legs on one expiry (`approaches.py:340-350`); `build_approach` then raises `adjust_needs_two_spreads` for every side
approach (`:708-709`), while A-27, A-36 and A-31 still build on any legs list (`:12-13`, `:705-707`); `tested_side` is None
(`:352-358`). **Still open:** the other trigger ids (T-04, T-06b, T-08, T-11 family, T-12 to T-20b) were not read one by one;
the `side_scope.json` trigger half is filled while its guard test is written, from the same reading (one id per line, with
its function). Effect on the design: the approach half is already enforced by `_condor`, so `side_scope.json` needs only the
trigger half plus a test that every approach id that raises `adjust_needs_two_spreads` is marked `both` (a little smaller than
first sized; size stays L because of the page flow).
**Design.** (1) pure `ofo/adjustment/side_scope.py`: `closed_sides(entry_legs, open_legs) -> {call, put}`; a table
`side_scope.json` (trigger id / approach id -> `both` | `call` | `put` | `none`) with a guard test that every id of
`system_playbooks.json` has an entry. (2) the plan block shows, per rule, `not_applicable: call` -> "Not applicable: the call
side is closed". (3) when `closed_sides` becomes non-empty, `actionable_alerts.raise_actionable(kind='side_closed')` (answers
`add_legs` / `confirm_new_shape`); "add legs" opens the builder on that strategy with the closed side's legs pre-filled as
DRAFT paper orders (the leg door, never auto-placed); "confirm" stores `shape_name` on the strategy view (a display column
`strategies.shape_label`; the plan, its type and its stops are untouched, P3). Not confirmed: the alert is asked again
(re-raised on the next check as the same open row: P1 keeps one open row per rule; "asked again" = the row stays open and
shows the add-legs prompt first).
**Tests first:** `tests/test_side_scope.py`: entry condor, call legs both exited -> `{call}`; put side -> `{put}`; one leg
of a side exited (a partial side) -> `{}` (ambiguous: side not closed, assert no notice); all four exited -> strategy closed
(no notice, P1 closes it); adjustment that rolled a leg -> not "closed". `tests_app/test_side_closed_alert.py`: the 25 Nov
strategy 168 after the two call exits: one open `side_closed` row, shape name unchanged, plan name unchanged; answer
`confirm_new_shape` -> label "Bull Put Spread", rules unchanged; answer `add_legs` -> strategy still named "Iron condor", no
order stored; never an order without the user (assert `paper_orders` unchanged after every answer). Frontend: every rule line
of the closed side prints the exact sentence; remaining-side rules show their value.
**Depends on refactor:** `StrategyBuilderPage.vue` and the leg door (Phases 3, 4, 5) -> the pre-fill flow is **WAITS (Phase
5)**; the backend and the plan-block lines do not. **Size L, Tier B.** **Owner question:** none new (Q2b covers closed-before-answer).

### P8 Playbooks and plans (S-17, S-11)

**Spec basis.** ADR-330 (9) in full: several standard playbooks per type ("SPEC CHANGE: REQ-158 ... becomes several standard
playbooks per strategy type"); the user's own playbooks by copy, edit and save under his name; "Two levels only ... 'Save this
plan with a name' makes it one of the user's own playbooks; there is no separate list of saved plans"; a plan shows every
condition of its playbook, each can be changed or switched off for this trade, "He cannot add a condition the playbook does
not have"; "Reset to playbook": after one confirmation every condition goes back, and "the plan marks the conditions the user
changed or switched off"; "a strategy is offered only the playbooks written for its own type".
**Verified [fix].** One system playbook per type is enforced in the database: `UNIQUE (strategy_type) WHERE is_system`
(`0031_adjustment_playbooks.py:396` `SYSTEM_INDEX`), `_SELECT_SYSTEM` returns one row (`playbook_store.py:279`), system versions are keyed by
type (`system_playbook_versions`, `playbook_store.py:285-286`), the seed has 12 entries (`system_playbooks.json`, 12
playbooks, names "<type>: system default"). Copy / edit / save-as: works (`playbook_store.create :587`, `duplicate :595`,
`rename :601`, `save_in_place :613`, `delete :626`); the plan is a copy with a `playbook_id` pointer (`accept_plan :664`);
the type list is `list_for_type` (`:565`, own type only: works). The plan sheet shows four fields only
(`AdjustPlanSheet.vue:25-38`); the full per-condition editor is a different page "Rules for this trade only"
(`adjustPlan.js:78` `customiseUrl`), and `customise()` leaves the sheet without saving (`AdjustPlanSheet.vue:142-146`, S-11).
No Reset, no changed marker. The active-playbook pointer (`adjustment_playbook_active`, one per user and type) is used by
`resolve` (`:226`, removed by P2) and `active_for`.
**Design (reuse first).** Keep `adjustment_playbooks` and `system_playbook_versions`; migration: drop the one-system-per-type
unique, add `slug` (stable per standard playbook, UNIQUE per type), re-key system versions by playbook id; seed the existing
12 as the first standard playbook of each type (names unchanged, no new content: the content is the owner's, Q6). The plan
sheet becomes the full condition list: for each trigger of the playbook body `{value fields, on/off}`; a pure
`ofo/adjustment/plan_diff.py` `diff(plan_body, playbook_body) -> {changed: [...], switched_off: [...]}` and `reset(plan_body,
playbook_body)`; `check_body` gains `subset_of(plan_body, playbook_body)` (no key the playbook lacks: "cannot add").
"Customise triggers" is removed from the sheet because the sheet now IS the editor (S-11 gone by construction); the old page
stays reachable from Strategies > Adjustments for editing the user's own playbooks. Reset route
`POST /strategies/{id}/adjustment-plan/reset` (one confirmation in the browser, the server does the copy).
**Tests first:** `tests/test_plan_diff.py`: identical -> empty diff; value changed -> listed; condition switched off ->
`switched_off`; added key not in the playbook -> `subset_of` False -> refused naming the key; reset -> equals playbook body.
`tests_app/test_playbooks_several_standard.py`: two standard iron condor playbooks coexist (red today: unique index);
a user is offered both plus his own and NOT a credit-spread playbook (type filter, answer: empty list for a type with none
-> the sheet says so); a plan made from one is unaffected by an edit or removal of the playbook (copy, as today); Reset with
the source playbook deleted -> refused with the catalogue sentence, plan unchanged (not found); Reset on a plan saved
before this change (`playbook_id` null, absent) -> refused, not a silent no-op; three iron condor strategies run three
different plans side by side (assert three `plan_for` bodies distinct); "Save this plan with a name" creates an own playbook
and adds no list of plans (assert table list unchanged except `adjustment_playbooks`); `check_body` refuses a plan with an
added condition. Frontend: changed rows carry a marker with the playbook's value; Reset needs one confirm; sheet with the
type's playbooks only.
**Depends on refactor:** none (`playbook_store.py`, `AdjustPlanSheet.vue`, `adjustPlan.js` are in no refactor row);
`StrategyBuilderPage.vue` mounts the sheet (no change needed). **Size L, Tier A** (migration). **Owner question:** Q6 (the
content of the standard playbooks is his; built meanwhile: the mechanism and the 12 existing ones).

### P9 Stand-alone condition checks and the one exit function (OD-2)

**Spec basis.** ADR-330 (12): "one exit function ('exit this strategy: these legs, this reason') that any trigger calls, and
each condition its own stand-alone check (index level, leg price, P&L amount, P&L percent, time of day) that only answers met
or not met. The one exit function is Phase 4 of the modular-doors plan; the checks and the one actionable-alert module follow
it." Plan levels raise alerts (ADR-330 (5)(b)); only Stops-panel triggers call the exit.
**Verified.** [fix] the exit block is inside `_fire` (`paper_monitor.py:205-246`), reached only by a crossing; plan levels are
checked in the background checker and only alert. [refactor] Phase 4 plans `exit_strategy(strategy_id, reason, kind,
price_source, only=None)` in `be/paper_exit.py`; the trigger judge `check_trigger_levels` exists (Phase 1).
**Design.** New package `backend/ofo/checks/`: pure functions `index_level(level, dir, spot)`, `leg_price(level, dir, price)`,
`pnl_amount(level, pnl)`, `pnl_percent(level_pct, pnl, max)`, `time_of_day(date, at, now)`; each returns `Met | NotMet |
NotComputable(reason)`. The P4 and P5 checks ARE `pnl_amount` and `time_of_day` (P4/P5 write them there, not in the evaluator).
The monitor's crossing judgement becomes `index_level` / `leg_price` and then calls `exit_strategy`. Nothing is added to the
Stops panel (no armed P&L exit: ADR-330 (5) "Not chosen: an auto-exit switch"); the structure only makes a later switch cheap.
**Tests first:** one file per check, the three answer states each plus boundaries (level equals price -> Met, both directions);
`test_monitor_uses_checks.py`: a leg stop and an index exit fire exactly as before (existing `test_paper_monitor.py` unmodified,
the golden rows of refactor Phase 4); a guard `tests/test_checks_no_side_effects.py` (AST: nothing under `ofo/checks/` imports
a store, a clock or a route; every function has no `conn` parameter).
**Depends on refactor:** WAITS (Phase 4: `exit_strategy`, `paper_monitor.py`). **Size M, Tier A** (exit path).

### P10 The live Plan watch box (OD-5)

**Spec basis.** ADR-330 (13): "one line per trigger (profit target, loss stop, each adjustment rule, the Stops-panel index
exits and leg stops) showing fires at / now / distance / state, in rupees and percent, live, from the one engine (ADR-008).
Shown only when the strategy has a plan; otherwise the line of point (11)."
**Verified [fix].** The evaluator already returns every rule's value, true or false (`Evaluation.values`, `playbook_eval.py:323`)
and the limits of the target and stop (`Evaluation.limits :324`); the screen route `GET /api/strategies/{id}/adjustment-check`
(`routes/adjustment_check.py:424-`) builds today's lines; the tracking panel shows only fired rules, in %
(`TrackingPanel.vue`, 266 lines; `readExits :176` reads armed index exits). Armed Stops-panel triggers come from
`GET /paper/strategies/{id}/triggers` (`PaperStops.vue:80`).
**Design.** New server read `GET /strategies/{id}/plan-watch` composing three sources into one list of `{label, fires_at,
now, distance_rs, distance_pct, state}`: plan rules from `Evaluation.values` + `limits`; armed triggers from the trigger store;
money formats from `strategy_money_view` (**WAITS Phase 3**; Wave 1 uses `adjustment_check.state_of`'s figures). New component
`PlanWatch.vue`, mounted on the builder page and on the Positions row; its refresh uses the book-read token of
`usePaperBookRead` (no timer of its own) and `priceState` for a paused/not-live row (a dash and the reason, never an old
number).
**Tests first:** `tests_app/test_plan_watch.py`: the 25 Nov strategy with plan: lines for T-07 target, T-06 stop, 2x-credit, one
index exit, two leg stops; each has fires-at, now, distance, state in {watching, fired, not applicable (P7), not computable};
a strategy with no plan -> the P2 sentence and an empty list while armed triggers STILL listed under their own heading
(they keep working, ADR-330 (11)); prices not live -> state `paused` and no `now` (assert absent, not 0); unreadable
evaluation -> neutral error, no lines (fail closed). Frontend: component test with the three states.
**Depends on refactor:** screen mount in `StrategyBuilderPage.vue` / `PaperStrategies.vue` WAITS (Phases 3 to 5); server read
does not. **Size L, Tier B.**

### P11 S-15, the server line (Paper totals include a closed trade the list hides)

**Spec basis:** none (searched: "Show closed", "closed positions"); ADR-330 (10) keeps Real and Paper totals separate. **Verified
[fix]:** `routes/paper.py:1121` `_totals` sums every strategy that can be priced and counts only the expired ones as left out
(`left_out_count :470`); the list hides closed rows unless `showClosed` (`lib/paperList.js:192-195`). Real case 25 Nov: the gap
was exactly Held IC k10's closed result. **Design:** add `closed_count` and `closed_text` ("Includes N closed strategies;
tick Show closed positions to list them") to the totals, from the server (the `_left_out_text` pattern, `:1178`); the screen
prints it (Q2). **Tests first:** totals with one closed and one open strategy -> `closed_count == 1`, text names 1; none closed
-> `None`; closed strategy of another user not counted; closed hidden-by-delete not counted. **Size S.** **Owner question:** Q11.

### P12 S-07, the word "Strategies" in the top menu

**Verified [fix]:** the label is NOT dead text: it is a `router-link` to `firstBuiltPath(key)` (`AppHeader.vue:263-269`,
`@click="closeMenu()"`), and `firstBuiltPath('strategies')` is `/strategies/my-strategies` (`router/nav.js:18`, `:91-94`).
So where S-07 was seen (on My Strategies, S-05) the click is a same-route navigation (nothing happens) and `closeMenu()` shuts
a menu that hover had opened (`onSectionEnter :180`). Only the toggle button opens the menu by click (`:271-281`,
`onToggleClick :133`, `data-testid nav-menu-toggle-<key>`). **Fix (changed from the first draft):** keep the link, and make a
click on the label open the menu when the page is already at the section's first path (otherwise navigate as today, menu
closed); Enter / Space on the toggle unchanged. Putting the label inside the button would remove the link, so it is not done.
**Tests first:** on the section's own first path, a click on the label opens its menu (and again closes it); on another path the
click navigates to `firstBuiltPath` (menu closed, as today); Enter / Space still work (`onToggleKey :146`); click inside the
open panel does not toggle. **Size S.** **Spec basis:** none (searched: "top menu");
`AppHeader.vue` header comment "each section opens a menu of its REQ-009 items".

## 4. Lane Q, the screens

### Q1 My Strategies cluster: bulk delete (S-01) with S-04, S-03, S-05, S-02

**Spec basis.** ADR-330 (8): "My Strategies gets a tick box per row, 'Select all' and 'Delete selected'. One confirmation names
how many will be deleted. Every rule of a single delete applies to each row (ADR-292, ADR-293): a strategy that cannot be
deleted today (for example one with open positions) is skipped and named in the result, as in '12 deleted, 2 kept: they have
open positions'." ADR-293 (1): delete is offered on a strategy whose only orders were paper, "open or closed".
**Conflict found:** ADR-330's example ("one with open positions") disagrees with ADR-293 (1) and with what the owner did on
25 Nov (a Running paper strategy was deleted one by one). The rule that decides is `can_delete` (no plan row, no version row,
not held: `strategy_store.py:122-125` `_DELETABLE_SQL`). Question Q5.
**Verified [fix].** One delete = `readRevision` (a GET) then `DELETE /strategies/{id}?expected_revision=N`
(`strategyActivity.js:84-125` `useDeleteFlow`; route `routes/strategies.py:507`; store `strategy_store.delete_draft :342`);
the control `DraftDelete.vue`; the list `MyStrategiesPage.vue:139-185` (Completed list is the same page, `completedOnly`).
Undo exists per delete (`:undoDelete`).
- **S-04:** on confirm the row action cluster swaps Delete for `delete-confirm-box` (`DraftDelete.vue:63`) in the same
  `flex-wrap` cluster as Rename (`MyStrategiesPage.vue:159-163`), so Rename lands under the mouse. **Fix:** the confirm renders
  as its own full-width line below the row (`col-span-full`, like the rename form `:174`), Rename and Delete keep their cells.
- **S-03:** the refusal text for a held-at-broker strategy says "Orders were already sent" (`templates.py:961`,
  `strategyActivity.js:8`, tests `test_strategy_delete_app.py:33,:432`). ADR-292 is the reason. **Fix:** a second catalogue
  sentence "This strategy is marked as held at your broker, so it cannot be deleted." chosen when the row has a held entry;
  needs one flag in the list row (`strategy_held_entries` exists, `strategy_store.py:125`). Wording is pinned by
  `tests/errors/template_pins.json`: both sentences added with pins.
- **S-05:** `list-loading` shows bare "Loading..." (`MyStrategiesPage.vue:139`) while the list read takes 1.5 to 4.5 s. Spec
  basis: ADR-320 line 32 "never stay on 'Loading'" (failure case). **Fix:** the same `LoadFailed` / skeleton pattern other
  lists use (`LoadFailed` in `AdjustPlanSheet.vue:10`, component `components/common/LoadFailed.vue`); a read that takes more than the page's limit shows the retry. Not a
  speed fix. **Verified [fix] (shape of the read):** `GET /strategies` runs five reads in series (`routes/strategies.py:443-453`:
  `store.list_strategies`, `closed_figures_many`, `_tracked_ids`, `_open_opportunities`, `current_legs_many`); the closed-row
  batching (`67a5cd06`, branch `perf/strategies-list-batch`) is already an ancestor of `e01f747`. **Still open:** which of the
  five takes the 1.5 to 4.5 s on an EMPTY list (cost cannot be per-row there); code cannot settle it. Access: time the five calls
  on the owner's account (a `log.info` with each call's seconds, or `EXPLAIN ANALYZE` of `_LIST` and the three account-wide reads).
- **S-02:** "An unexpected server error (ERR-6960F002)" once on Delete of a Running paper strategy, retry worked. **Cause
  still open (needs the owner's API log).** First command: `grep -rn "6960F002" <api log>` (the owner's PC log). **Verified
  [fix] (how the line reaches the log):** the id is `"ERR-" + secrets.token_hex(4).upper()` (`errors.py:611-612`) and the handler
  writes `log.error("unhandled error %s on %s %s", ..., exc_info=exc)` (`errors.py:617`), so the matching log line carries the full
  traceback and names the exception class; nothing else settles it. **Verified [fix] (what can and cannot be the 500):**
  `DELETE /strategies/{id}` is `routes/strategies.py:507-516`; `_run` (`:417-428`) turns only `StrategyStoreError` /
  `StoredFormError` into a sentence and re-raises everything else, so a raw 500 is a non-store exception. Candidate (b) below is
  ruled OUT: a stale `expected_revision` raises `StrategyStoreError(REVISION_CONFLICT)` (`strategy_store.py:200-204`), a handled
  409. `_deletable` (`:333-339`) swallows its own errors and fails closed (a 409). That leaves a database error out of `_locked`
  (`SELECT ... FOR UPDATE`, `strategy_store.py:161-163`, `:378-383`): the app role has `statement_timeout = 30s`
  (`alembic/versions/0001_baseline_ledger_clock.py:46,266`), so a row lock held longer than 30 s, or a deadlock with the monitor /
  worker, raises a DB error and ends as ERR-xxxx. Candidate causes to test, in this order: (a) lock wait between `delete_draft`'s row lock (`_locked`) and
  the paper monitor / worker holding the same strategy row; (b) `expected_revision` race: **ruled out** (a handled 409, see above); (c) a monitor tick writing to a hidden strategy.
  Tests-first: reproduce with a DB test that runs `delete_draft` while a second connection holds `FOR UPDATE` on the row and
  a trigger is armed; assert a clean refusal sentence, never a 500. If the log shows another cause, the test follows it.
**Design for bulk delete (reuse):** one server route `POST /strategies/bulk-delete {items: [{id, expected_revision}]}` that
calls `store.delete_draft` per id inside its own savepoint and returns `{deleted: [ids with revision], kept: [{id, reason}]}`;
the browser keeps ONE Undo list. Tick boxes with "Select all" (only visible rows after the search filter; the count says so).
Existing single-row Delete unchanged. **Why a new route and not N calls:** one confirmation, one result with reasons, one
Undo window; each id still passes the same `_deletable` rule (no second rule).
**Tests first:** `tests_app/test_strategy_bulk_delete.py` (DB): 14 strategies = 12 deletable + 1 held (k10) + 1 real-basket:
result 12 deleted, 2 kept with reasons held / basket; another user's id -> kept "not found" (never leaks existence: same as
single delete 404 -> the item reported as "not found"); already hidden id -> reported not found; stale revision -> kept
"changed, reload"; empty list -> 422 refused; duplicate ids -> deleted once; more than 200 ids -> refused (limit stated);
one id raising -> that item `failed`, the others still deleted (savepoint per item); Undo of the batch restores exactly the
deleted ids. Frontend `my-strategies-bulk.test.js`: tick two rows -> "Delete selected (2)"; confirmation text names 2; Select
all selects only visible rows; held row has no tick box and shows the held sentence; result line exact "12 deleted, 2 kept:
they have open positions" style (reasons from the server); S-04: after clicking Delete, the element at the Delete position is
still Delete's confirm or nothing, never Rename (assert layout: Rename's bounding box unchanged before and after).
**Depends on refactor:** `MyStrategiesPage.vue` is edited by Phase 6 F8 (`:116-117` rename pre-read removed); the strategy rows
of `strategy_store.py` get `owns` in Phase 7 R2. **WAITS (Phase 6/7 merged)** for the frontend; the server route and the
S-02 investigation are Wave 1 but Lane Q starts with S-02. **Size M, Tier B.** **Owner question:** Q5.

### Q2 One Positions list for real and paper (OD-1) with S-28, S-23, S-19, S-26, S-15

**Spec basis.** ADR-330 (10): "SPEC CHANGE to ADR-201 (2), which chose a separate Paper tab. Every paper row carries a clear
'PAPER' tag (not only a small 'P'). The top shows two totals, 'Real P&L' and 'Paper P&L', never added together ... Filter
buttons All / Real / Paper, default All. Every exit confirmation names 'Paper' or 'Real (Zerodha order)' in its title. Real
rows still come from Zerodha first (ADR-016); real contracts are grouped by strategy."
**Verified [fix].** `PositionsPage.vue:26` two tabs `positions` / `paper`; `:93-95` `Tabs` + `PaperStrategies`; the real
table is `:128-149` (contract, units, Zerodha, status) with no exit (real orders are frozen, ADR-281); the paper component
`PaperStrategies.vue` (352 lines) also serves the builder's compact list (`compact`, `:43`); totals from `/paper/strategies`
(`paperList.js:158-166`), real from `/positions` (`routes/positions.py`). "Real (Zerodha order)" in an exit title has no
action to name today (ADR-281): the title text is built and tested, the button stays hidden.
**Design:** a Positions page with one list: real rows then paper rows grouped by strategy, each paper row `PAPER` tag
(`data-testid=paper-tag`), two totals (reuse the two existing readers, no new arithmetic), filter buttons, the paper tab's
`PaperStrategies.vue` rendered inside; `?tab=paper` links keep working and set the filter to Paper (the compact builder list
and `PaperStrategies.vue:46` link keep their `tab=paper` query). Exit confirm titles: `PaperConfirmDialog.vue` title gets the
word from one function `positionKind(row)`.
- **S-28:** `PaperStrategies.vue:148` shows `paper-add-orders` on every group including Completed (`g.statusWord ===
  'Completed'` is available, `:68`). Hide it for Completed (Q10). Test: Completed row has no `paper-add-orders`; a Running one
  does; "Open in Builder" stays.
- **S-23:** `PaperStops.vue` reads its triggers once on mount (`:80`) and after its own actions, so a fired stop stays "armed" until
  reload. Fix: re-read when the list's `goodReadToken` changes (already passed in, `PaperStrategies.vue:154`). Test: stop armed ->
  the book read shows the leg closed -> the panel row reads "fired" within one refresh (fake timers; assert no extra timer is
  created, uses the token); read fails -> keeps the last good list with the failure line (as `NEUTRAL_ERROR` today).
- **S-19:** the panel asks for an index level and never shows the index now. Reuse the index reader that `IndexStrip` uses (one
  source); show "NIFTY now 25,735.00 as of HH:MM:SS" or the `priceState` not-live text. Spec basis: none (searched: "Stops
  panel"). Test: value shown equals the strip's; feed down -> text names it, no number.
- **S-26:** the panel moved 16 px mid-typing because a live refresh re-rendered the form block. Fix: the form block keys on
  strategy id only and reserves the height of the status line (so a message appearing does not shift the boxes); never
  re-mount inputs on a refresh. Test: type in a box, trigger a refresh and a status line, assert the input element is the
  same node and keeps focus and value, and its `offsetTop` is unchanged.
- **S-15 (screen half):** print P11's `closed_text` under the Paper total (Q11).
**Tests first (OD-1):** `tests/frontend positions-one-list.test.js`: default filter All shows real and paper rows; the tags and
the two totals; "Real P&L" and "Paper P&L" are never summed (assert no third figure and no number equal to their sum in the
DOM); filter Real hides paper rows and vice versa; a list with only paper rows (Zerodha not connected) shows the existing
"not connected" sentence for the Real part and keeps the paper rows (answer states: connected, not connected, read failed,
empty, ambiguous = a row carrying both a real contract and a paper strategy of the same name -> two rows, each tagged);
exit-confirm title contains "Paper" for a paper exit. Existing tests changed with reasons: `positions*.test.js`,
`paper-tabs*` that pin the two tabs (`ADR-201 (2)`).
**Depends on refactor:** Phase 4 edits `PaperStrategies.vue`, `PaperBookPanel.vue`, adds `ExitButton.vue`; Phase 3 edits
`TrackingPanel.vue`; G3 scans `PaperStrategies.vue`. **WAITS (Phase 4 merged)**; wave 2 only. **Size L, Tier B.**

### Q3 S-18 and S-14, links that go nowhere

- **S-18 (blocks the task).** Verified [fix]: `HomeOverviewPage.vue:121` is `<router-link to="/strategy/builder" ...
  :data-testid="recent-open-${s.id}">`, no id; working links use `{path:'/strategy/builder', query:{strategy:String(id)}}`
  (`PaperStrategies.vue:232`, `MyStrategiesPage.vue:96`, `AdjustCompare.vue:17`). Fix: the same object. Core: click `recent-open-168`
  from a FRESH page load and read the address and the strategy name (the owner's practice of 25 Nov; OD-4 is not started, this
  one test is part of the bug). **Tests first** (`home-open-strategy.test.js`): with two rows, each link's resolved `href`
  equals `/strategy/builder?strategy=<its id>`; clicking row 2 loads strategy 2's legs (mock `GET /strategies/2`), not row 1's;
  a row with no integer id has no link (answer: absent); a strategy the server says is not found -> the builder's
  `openError` text. A shared helper `lib/strategyLinks.js` `builderLinkOf(id)` replaces the four copies (kit: one home).
- **S-14.** Verified [fix]: `LiveStrategyCard.vue` renders figures and an adjustment-opportunity link only (`:205`), the name is
  plain text; the leg table header says "Planned entry" (`:240`) for paper fills; load text `:218`. Spec basis: ADR-207
  ("Open in Builder, Add orders, Exit" for paper positions); none found for the Live card (searched: "Live card"). Fix: the name
  links to the builder (`builderLinkOf`), plus Stops (`/positions/current-positions?tab=paper&strategy=<id>` as the
  compact list does, **until Q2 lands**) and "Exit" opens the same paper confirm (WAITS Phase 4 `ExitButton`; until then the
  link opens the builder). Header: "Entry price" for a filled leg, "Planned entry" only for an unfilled plan. **Tests first:**
  name link target; a Completed card shows no Exit; a card in `error` state shows no links; header word by state. **Size S each.**
  **Depends on refactor:** `LiveStrategyCard.vue` not in a refactor row; the Exit part waits.

### Q4 S-06 basis line, S-09 chain prices, S-25 orderbook columns

- **S-06.** Max Profit/Loss are after charges and breakevens before, with no basis line (case 25 Nov: Max Profit +3,619 =
  3,877 - 258 charges; breakeven 25,490 = 25,550 - 59.65). Spec basis: ADR-321 (2) breakevens "carry the same charges as Max
  Profit / Max Loss ... with a line saying so" (written for the paper book; the plan summary is the gap; same class as D-16).
  Verified [fix]: `SummaryCards.vue` prints Max Profit / Max Loss with the after / before charges text (`:29`) and the
  breakeven row (`:72-77`); the figures come from the engine: the summary's breakevens are made in
  `ofo/scenario/levels.py:279-298` (`breakevens = breakevens_with_shift(strategy, booked)` at `:286`, shift = booked only, so
  BEFORE charges), serialized by `ofo/outcome/serialize.py:309-311` (`breakevens_display(s.breakevens, out.spot_level)`; the one
  text maker is `breakevens_display :58`, `_breakeven :50`); the target-date path is `outcome/target.py:207-211`, `:297`
  (`breakevens_at`, booked counted, no charges). **Verified [fix], what it changes:** the after-charges kernel already exists:
  `book_breakevens` (`ofo/engine/extremes.py:191-208`) calls `breakevens_with_shift(strategy, view.cash - charges)` and
  `loss_regions_after_charges` (`metrics.py`) is used at `levels.py:296`; so the fix reuses `breakevens_with_shift` with the
  charges in the shift (no new math, size S stays). Fix choice: compute the
  breakevens after charges in the engine (one engine, ADR-008) or label both with their basis; recommendation: after charges
  with the line, because that is what the paper book does (ADR-321 (2)). **Tests first:** the 25 Nov plan: breakevens equal the
  after-charges pair (~25,494 / ~26,106) and the line "after charges" appears; charges unavailable -> before-charges breakevens
  with the line "before charges" (answer state: not computable); expiry vs target-date toggle unchanged.
- **S-09.** Pick from Option Chain shows "-" for 4-8 s (`LegPicker.vue:751,:856` "Reading strikes..."; the chain cells in
  `OptionChainPage.vue` / `useChainLive.js`). **Verified [fix] (cause of the dash, from code):**
  `GET /leg-picker/strikes` (`ofo_app/routes/leg_picker.py:734-753`) calls `_held_quotes` (`:401-410`), which takes the window
  lease (`LEASE.hold`, `:407`) and in the SAME call reads `provider.option_chain_snapshot` (`:409`); on a window not held before,
  the vendor has not streamed yet, so the cells come back null and the picker prints "-" (`_cell :320-332`: no quote -> no price).
  The page then refills only on its timer, `PICKER_REFRESH_MS = 5000` (`lib/legPicker.js:88`, `LegPicker.vue:426`), which is the
  4-8 s the owner saw (first frame ~0 s + one 5 s tick + the answer time). The first opening shows "Reading strikes..."
  (`LegPicker.vue:751,856`) until the GET returns, then prices within ~4 s, consistent with a warm lease. **Still open:** the
  exact vendor delay (ms) after `hold`; settled only by a live-feed run (market hours), command: two timed
  `GET /leg-picker/strikes` calls 0.5 s apart on a fresh window, count null `ltp` in each. **Fix:** the page re-reads once
  after about 1 s while any visible cell has no price (before the 5 s tick); the server may also wait a short bounded time
  for the first quotes after a fresh `hold`. Not decided here (Tier A for the server wait: it is feed code); recommendation: the
  page-side early re-read. Fix after the delay is measured; the
  rule is ADR-321 (9) (a price states its time) and the dash needs a reason ("waiting for prices"), never a bare "-". **Tests
  first:** while strikes are loading the cells read the loading reason and B/S buttons are disabled (they are clickable on dash
  rows today).
- **S-25.** Orderbook Qty and Price run together ("65101.20"). Verified: the table is the Orderbook view of `PaperBookPanel.vue:76-85`
  (`<table data-testid="order-table">`), not `PaperConfirmDialog.vue`. **Verified [fix] (cause):** Qty and Price ARE two cells
  (`:84` `order-qty`, `:85` `order-price`), both `num text-right`, but the table is a plain `w-full text-xs` table with no cell
  padding and the `<th>` are centred while the cells are right-aligned; two adjacent right-aligned cells with no padding touch,
  so "65" + "101.20" reads "65101.20" (and a 2-digit price leaves a gap). It is not the `ui-table` class (`style.css:62`).
  Fix: give the Orderbook table the `ui-table` class (or `px-2` on every cell), right-align the Qty and Price headers with their
  cells, `tabular-nums`. **Test (changed: the two cells already exist):** `order-qty` and `order-price` cells carry horizontal
  padding and the same alignment as their header (class assertion), and the row text with `65` and `101.20` has a separator
  element or padding between them.
  **Sizes:** S, S/M, S. **Depends on refactor:** `LegPicker.vue` is Lane B's file in refactor Phase 5 -> S-09 WAITS (Phase 5).

## 5. Ownership, lanes, merge order, ADR numbers

Lane rules (parallel-sessions rules in `docs/process/builder-scope-briefs/LANE-A-B-INDEX.md` and `PLAN-phases-3-8.md` section 3):
split by files not by bug; one branch per lane cut from the SAME commit; a lane edits only its own rows; ONE ADR-number list
held by the coordinator; fixed merge order; merge, never rebase; after each merge regenerate generated files and grep for
functions one side removed that the other still calls.

Branches (names are suggestions): **Lane P** `feat/nb-plan-alerts-1126`, **Lane Q** `feat/nb-screens-1126`, both cut from the
same commit: Wave 1 = the head of `fix/ic-live-test-1123` at the time; Wave 2 begins when each lane runs `git merge
origin/refactor/modular-doors` (owner's word first; `PLAN-phases-3-8.md` section 1: "Never merge ... into `fix/ic-live-test-1123`
until the owner says so"; a lane branch merge into a feature branch is not that merge, but the coordinator should say so).

Paths: `be/` = `backend/ofo_app/`, `fe/` = `frontend/src/`, `ft/` = `frontend/tests/`.

| Path | Lane | Items |
|---|---|---|
| `backend/ofo/alerts.py` (new), `be/actionable_alerts.py` (new), `be/notifier.py`, `be/background.py`, `be/playbook_store.py` | P | P1, P2, P8 |
| `be/paper_trigger_store.py`, `be/paper_monitor.py` (wave 2), `be/routes/paper.py` | P | P1, P6, P11 |
| `be/adjustment_check.py`, `be/settings_in_force.py`, `be/adjustment_readers.py`, `be/paper_limit.py` | P | P2, P3, P4 |
| `backend/ofo/adjustment/**`, `backend/ofo/checks/**` (new), `backend/ofo/engine/extremes.py` | P | P4, P5, P6, P7, P8, P9 |
| `be/routes/adjustment_plan.py`, `be/routes/adjustment_check.py`, `be/routes/adjustment_history.py`, `be/routes/system_playbooks.py`, `be/routes/playbooks.py`, `be/system_playbook_store.py` | P | P2 to P10 |
| `be/alembic/versions/**` (the ONLY lane that adds migrations) | P | P1, P3, P8 |
| `fe/lib/paperAlerts.js`, `fe/lib/adjustPlan.js`, `fe/lib/infoPopup.js` (new), `fe/composables/useToast.js`, `fe/components/layout/ToastHost.vue`, `fe/components/layout/AppHeader.vue` | P | P1, P12 |
| `fe/pages/AlertsPage.vue`, `fe/pages/AdjustmentsPage.vue`, `fe/pages/AdjustmentOpportunitiesPage.vue` | P | P1, P8 |
| `fe/components/strategy/AdjustPlanSheet.vue`, `PlanEntry.vue`, `TrackingPanel.vue`, `PlanWatch.vue` (new), `AdjustCompare.vue` | P | P2 to P10 |
| `fe/pages/StrategyBuilderPage.vue` | P (after refactor Lane A hands it over, `PLAN-phases-3-8.md` 3.2) | P7, P10 |
| `tests/test_actionable_alert_one_module.py`, `ft/one-popup-module.test.js`, the new tests of P items | P | P1 to P11 |
| `be/strategy_store.py`, `be/routes/strategies.py`, `backend/ofo/errors/templates.py` (the S-03 sentence only) | Q | Q1 |
| `fe/pages/MyStrategiesPage.vue`, `fe/components/strategy/DraftDelete.vue`, `DraftDeleteStatus.vue`, `fe/lib/strategyActivity.js` | Q | Q1 |
| `fe/pages/PositionsPage.vue`, `fe/components/strategy/PaperStrategies.vue`, `PaperStops.vue`, `PaperConfirmDialog.vue`, `fe/lib/paperList.js` | Q | Q2 |
| `fe/pages/HomeOverviewPage.vue`, `fe/components/live/LiveStrategyCard.vue`, `fe/lib/strategyLinks.js` (new) | Q | Q3 |
| `fe/components/strategy/SummaryCards.vue`, `backend/ofo/outcome/**`, `fe/components/strategy/LegPicker.vue` (after refactor Lane B), orderbook table files | Q | Q4 |
| `spec/**`, `views/**`, `docs/process/coverage-stages.yaml`, `docs/api/openapi.json`, `tests_app/reply_inventory.py`, `tests/errors/template_pins.json` | coordinator | regenerated after each merge, never hand-edited by a lane |

Overlaps and how each is handled: (1) `fe/components/layout/AppHeader.vue` is P's alone (bell and S-07). (2) `routes/paper.py`
is P's alone; Q's S-15 and Plan-watch mounts consume P's new fields after merging P. (3) `PlanWatch.vue` is P's file; Q adds the
one import and tag in `PaperStrategies.vue` after merging P. (4) Migrations: only P; Q has none. (5) Files the refactor lanes own
(`paper_monitor.py`, `PaperStrategies.vue`, `MyStrategiesPage.vue`, `LegPicker.vue`, `StrategyBuilderPage.vue`,
`TrackingPanel.vue`) are edited only in Wave 2.

**Merge order.** 1) refactor lanes finish and merge as their plan says (`PLAN-phases-3-8.md` 3.3). 2) Lane P Wave 1 -> main
line; 3) Lane Q merges P, then Q Wave 1 -> main line; 4) both lanes merge the refactor head, run Wave 2; 5) P first, then Q.
Before any merge: the preflight, the changed tests, `merge_audit.py`; after: regenerate `views/spec-digest.md`, coverage
register, OpenAPI and reply inventory, and grep for removed callers (notably `playbook_store.open_suggestion`,
`paper_trigger_store.add_alert`, `Resolved("active"|"system")`, `active_for`).

**ADR numbers: from the coordinator's list.** Decision rows this plan needs (numbers NOT assigned here; the refactor's Lane B
may claim ADR-331): (1) the alert classes and kinds (informational vs actionable list, Q2) and the superseding of ADR-237 (4)
lapse for actionable records; (2) the rupee-level basis (Q3); (3) the time exit date field, superseding ADR-310 (2); (4)
the stop base rule after an adjustment (Q4); (5) several standard playbooks (REQ-158, REQ-169 text); (6) OD-1, superseding
ADR-201 (2); (7) the side-closed question and the plan's shape label (ADR-330 (2) holds the text; row only if the shape label
column needs a rule); (8) bulk delete result and reasons (ADR-330 (8) holds the text; only if Q5 answers "skip running").
Each is written with its section text before or with the code, the same turn (spec-first R4). Spec text edits needed:
REQ-158, REQ-161, REQ-169, REQ-109 AC-8 (stop alerts informational), ADR-295 / ADR-214 "No plan saved yet" lines.

## 6. Owner business questions (each with spec basis, real case, options, recommendation, built meanwhile)

Format: `Spec basis` line, then the question. None blocks the first step of any item.

- **Q1 Direction.** Spec basis: `docs/process/standing-direction.md` rule 2 (iron condor freeze) and rule 4 (owner request outside
  the order: one question, "change of direction or one-off exception"); ADR-330 is the owner's explicit words of 25 Nov.
  Real case: ADR-330 adds new plan triggers (rupee levels, time exit any day) and several playbooks, which the freeze lists as
  depth. Options: (a) record ADR-330 as a one-off exception, order unchanged; (b) change the direction; (c) hold until step 4
  closes. Recommendation (a). Built meanwhile: P1 to P3 and the bugs, which are defects or part of step 4 item 10.
- **Q2 Is a fired Stops-panel exit (leg stop, index exit) actionable or informational?** Spec basis: ADR-330 (3a) names plan
  levels and adjustment rules as actionable, (3b) "nothing for the user to do ... settled at expiry, stop saved" informational;
  the fired stop is not named. Real case 25 Nov: 26000 CE stop fired 12:53:00, the exit was already recorded. Options: (a)
  informational pop-up + History (nothing to answer: the trade is already exited); (b) actionable "acknowledge". Recommendation
  (a). Built meanwhile: (a). **Q2b** what happens to an unanswered alert when the whole trade closes first: recommendation, the
  row closes as `closed_by_system` and is kept in History (the question has no position left).
- **Q3 Rupee levels: before or after charges, whole trade or per lot?** Spec basis: ADR-330 (5) is silent; the percent target
  is before charges (screen note 25 Nov, "the dialog does not say"). Real case 25 Nov: "Rs 1,000 per lot" profit and "Rs 400
  per lot" loss on a 1-lot, Rs 3,900 / Rs 2,600 trade. Options: (a) whole-trade rupees, before charges, per-lot figure shown
  beside it; (b) per lot; (c) after charges. Recommendation (a), because every other plan level is before charges and the plan
  shows both figures. Built meanwhile: (a), the basis printed on the sheet.
- **Q4 Does an adjustment (a roll or any app-placed adjustment) move the fixed stop base?** Spec basis: ADR-330 (1) "worked out
  ONCE, from the trade as entered ... change only when the user edits the plan". Real case: none in the last 14 days (adjustments
  have not fired live). Options: (a) strict, only a plan edit moves it; (b) re-base once with a notice at an adjustment.
  Recommendation (a). Built meanwhile: (a).
- **Q5 Bulk delete of Running paper strategies.** Spec basis: ADR-330 (8) example says a strategy "with open positions" is
  skipped; ADR-293 (1) allows delete of paper strategies "open or closed". Real case 25 Nov 09:50: "T1123-C9 pm 4lot" (Running)
  was deleted one by one. Options: (a) same rule as single delete (delete them; confirmation says "N of them are running");
  (b) skip Running ones. Recommendation (a). Built meanwhile: (a), the one rule `can_delete`.
- **Q6 The content of the standard playbooks** (names, conditions, how many per type). Spec basis: ADR-330 (9) "the product team
  writes the STANDARD playbooks ... details still being asked". Real case: none yet (the owner "will explain how to build the
  standard versions"). Built meanwhile: the mechanism and the existing 12 system defaults as the first standard playbook.
- **Q7 No plan and the adjustment limit.** Spec basis: ADR-330 (11) "no adjustment suggestions"; REQ for the limit not read.
  Real case: `paper_limit.py:43` reads the plan's limit when a manual adjustment order is placed. Options: (a) no plan = no limit
  applies; (b) the type's default limit still applies. Recommendation (a). Built meanwhile: (a).
- **Q9 Time exit: one date and time, or a daily time?** Spec basis: ADR-330 (7) "any trading day and time". Real case 25 Nov:
  "exit at 15:15 today" on a 1 Dec trade. Options: (a) one date and one time; (b) every trading day at a time until expiry.
  Recommendation (a). Built meanwhile: (a), blank date = expiry day (today's behaviour).
- **Q10 "Add orders" on a Completed strategy (S-28).** Spec basis: none (searched: "Add orders", "Completed"); ADR-299 (1)
  Completed = no open leg. Options: hide; keep. Recommendation hide (Open in Builder stays). Built meanwhile: hide.
- **Q11 Paper total includes closed trades (S-15).** Spec basis: none; ADR-330 (10) totals stay separate. Options: (a) keep the
  total, print "Includes N closed strategies"; (b) exclude closed from the total. Recommendation (a): the total is the account's
  paper result, only the list is filtered. Built meanwhile: (a).

(Q8 is not asked: a fired alert's Exit answer opens the usual confirmation, ADR-003, nothing to decide.)

## 7. Confidence per item and the first command that verifies it

Confidence = that the plan's facts and steps are right as written (not that the build is easy).

| Item | Confidence | Unverified | First command |
|---|---|---|---|
| P1 | 85 % | migration trigger on `adjustment_suggestions`; every caller of `lapse*` | `grep -rn "playbook_store.lapse\|open_suggestion\|record_held\|add_alert" backend/ofo_app --include=*.py` (count callers; expect 8 sites listed in section 2) |
| P2 | 90 % | what `paper_limit` does with `body None` | `python -m pytest -c pytest-app.ini tests_app/test_adjustment_check.py -q` after editing `resolve` (db_run.py) |
| P3 | 75 % | an "entry orders only" engine call exists (the plan assumes `price_after` on entry-kind orders) | `grep -n "def price_after" -A12 backend/ofo_app/routes/adjustment.py` and a scratch call on strategy 168's stored orders |
| P4 | 80 % | where T-07's percent is turned into rupees for the "Rs" figure | `grep -n "of_max\|rupee" backend/ofo_app/routes/adjustment_plan.py` |
| P5 | 85 % | other readers of `time_exit` (A-35 approach, `exit_inputs_of`) | `grep -rn "time_exit" backend --include=*.py` |
| P6 | 85 % | pricing the stop level as a "given price" in `exit_risk` | `python -m pytest tests/test_exit_risk.py -q` (name unverified: `grep -rln "exit_risk" tests tests_app`) |
| P7 | 75 % | trigger ids T-04, T-06b, T-08, T-11 family, T-12 to T-20b not read one by one (approaches settled: `approaches.py:340-350`, `:708`); the shape label store | `grep -n "shorts\|kind ==" backend/ofo/adjustment/playbook_eval.py backend/ofo/adjustment/approaches.py` |
| P8 | 70 % | `system_playbook_versions` keyed by type in 0034/0041; admin page assumptions | `sed -n 1,60p backend/ofo_app/alembic/versions/0034_system_playbook_versions.py` |
| P9 | 70 % | exact `exit_strategy` signature after Phase 4 | `git show origin/refactor/modular-doors:backend/ofo_app/paper_exit.py` (exists only after Phase 4) |
| P10 | 75 % | `Evaluation.values` is filled on the check route path, not only the worker's | `grep -n "values=" backend/ofo/adjustment/playbook_eval.py` |
| P11 | 90 % | none | `python -m pytest -c pytest-app.ini tests_app/test_paper_list.py -q` (name unverified) |
| P12 | 90 % | none (the label is a router-link, `AppHeader.vue:263-269`) | `cd frontend && npx vitest run tests/` (the AppHeader test file; name unverified) |
| Q1 | 80 % | S-02 cause (not known); held flag in the list row | `grep -rn "6960F002" <API log>`; `python -m pytest -c pytest-app.ini tests_app/test_strategy_delete_app.py -q` |
| Q2 | 70 % | PaperStrategies after Phase 4; `/positions` row shape | `git show origin/refactor/modular-doors:frontend/src/components/strategy/PaperStrategies.vue \| head -120` |
| Q3 | 90 % | none | `cd frontend && npx vitest run tests/home.test.js` (then the new click-through test) |
| Q4 | 80 % | S-09 exact vendor delay after `hold` (live feed only); files now located: S-06 `scenario/levels.py:286`, S-09 `routes/leg_picker.py:407-409`, S-25 `PaperBookPanel.vue:76-85` | `grep -n "breakevens_with_shift" backend/ofo/scenario/levels.py backend/ofo/engine/extremes.py; git grep -n "order-qty" frontend/src` |

Core and proof (kit E3): the first run of Lane P is `tests_app/test_actionable_alerts.py::test_s16_real_sequence` on the 25 Nov
numbers; a failing core stops the lane. The first run of Lane Q is the Q3 click-through test (smallest, real ids) and the S-02
log read.

Not in this plan, by owner word: OD-4 (tests for every link and button): "do not do anything. I will let you know when to do
it" (screen-check file). D-ids other than those named (D-18, D-07, D-44, D-25, D-57) are outside S-02 to S-28 and stay in the
ledger.

## 8. Order of work for the first session (summary)

1. Lane P: migration + P1 core test + module + guards (wave 1), then P2, P3, P4, P5, P6 (route and panel line), P8, P7
   (backend), P10 (server), P11, P12. Wave 2: P1 monitor call, P6 alert line, P7 page flow, P9, P10 mounts.
2. Lane Q: S-02 log read, Q3, Q4 (S-06, S-25), then after Wave 2 merge: Q1, Q2, S-09.
3. Coordinator: ADR numbers, spec text, regenerated files, Q1 to Q11 asked when the owner is back (B2: nothing is asked while
   he is away; the built-meanwhile choices are all reversible by one line).
