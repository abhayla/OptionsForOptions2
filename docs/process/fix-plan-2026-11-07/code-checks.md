# Code checks behind fix plan v4 (7 Nov 2026 ~00:5x-01:0x IST)

Four read-only checkers (fresh Sonnet Explore agents, no edits, no runs) located every issue in the live tree
`D:\Abhay\Ventures\OptionsForOptions2-live` (code 514113f1) and the gate logs. Their reports are kept here as written,
condensed only in wording. "Verified" marks a line the lead re-read; everything else is the checker's claim. Minutes =
code + unit tests of the changed code only, expert who knows the codebase. B = backend/, F = frontend/src/.

Lead spot-checks (re-read 7 Nov): planned_entry.py:36-39 LTP first, mid only without LTP (verified); strategy_store.py
:115-116 _CAN_DELETE_SQL checks execution_plans + strategy_versions only (verified); MyStrategiesPage.vue:24
`COMPLETED_STATUSES = []` (verified); legEdit.js:167 note quotes `${leg.strike}` (verified); AdjustCompare.vue:216
`scope = ref(props.picked.length ? 'picked' : 'all')` (verified); paper_monitor.py:232 every trigger order kind "stop"
(verified); alert_gate.py:275 `elif state.opened_today >= preset.daily_cap` for every rule (verified);
background.py:749 `self._memory` in process only (verified); background.py:1144 `own = None if ... else user_values`
(verified); StrategyBuilderPage.vue:143 `Number(id)` (verified); config.py:46 DB_POOL_SIZE default 2 (verified);
approaches.py:465 `target_short_delta` strike pick exists (verified).

## 1. Rule engine and alerts
| Item | Files | What exists | Smallest fix | Overlap | Min |
|---|---|---|---|---|---|
| 65/89/36 | B/ofo_app/background.py:1187, :1180, :1229; playbook_store.py:250-252; new migration (0031 guard forbids deleting rows / changing held_at_entry) | `ev = pe.evaluate(w.body, state, known, None if known else state, ...)`; worker memory in process only, never loaded from the DB; screen: `elif not memory: entry = state` (adjustment_check.py:535-536) | seed worker memory from playbook_store.rule_state before the first evaluate; ADR-258: adjustment_no column or reset marker, re-baseline after a basket | 89 = 65; 36 = ADR-258 half | 90-120 |
| 49/45 (ADR-266) | adjustment_check.py:278-283 (ltp/pnl), :317-318 | ltp from rows; no bid/ask/mid logic in the file; _stop_hit (playbook_eval.py:702-715) has no cap | mark at mid when LTP outside bid/ask or older than the quote; loss > max_loss -> _Missing("inconsistent_prices") | paper P&L marking path not checked | 60-90 |
| 57/59/60/69/90 (ADR-267) | B/ofo/adjustment/alert_gate.py:275, :283; background.py:1144 | daily cap and `opened_today + 1` for every rule; :1144 passes a Mapping with no `.own` -> Unreadable(USER_VALUES_WITHOUT_OWN), likely cause of `gap_pct None` (inferred) | skip cap/count for level-watch and day rules; pass the `.own` record; day-rule text from the catalogue | 90 same text path | 75-100 |
| 63/64 (ADR-268) | adjustment_check.py:194-196 `_abs_delta`; playbook_eval.py:458-461 `_t01` | `abs(g.delta)`; T-01 uses abs(strike - spot), no breached branch | delta 1/0 at intrinsic + 1 tick; T-01 fires at/beyond the strike + wording | merge 63+64 | 45-60 |
| 81 | none extra | evaluate() puts a non-fired rule in `clear` and `values`, not `results` (playbook_eval.py:801-806); route returns ev.results only (routes/adjustment_check.py:262-264) | covered by 88 (T-19 is a passing rule, inferred) | duplicate of 88 | 0 |
| 88 | routes/adjustment_check.py:~48-60 (CheckResultOut, add kind "clear"), :262, :90 `_num`; F TrackingPanel.vue:94 | Evaluation.values carries RuleValue for every passing rule but nothing outputs it; T-11 `ge` inclusive | add a "passing" kind from ev.values; render in TrackingPanel | 81, 12 | 40-60 |
| 11/38 (ADR-260) | playbook_store.py:311-314 `_INBOX`; strategy_store.py:120; F lib/paperAlerts.js:60 | no `deleted_at IS NULL` filter; bell = paperAlerts.unread + openRecords | close a deleted strategy's open records or filter; 38 = one list UI | | 30 + 90 |
| ADR-270 | adjustment_check.py:355; entry_facts_store.py (no IV column); :310 state_of | `if not t14.get("on") or scenario_mode.current() is None: return state`; entry_atm_iv only from a scenario | T-14: drop the scenario test; T-11: entry_atm_iv column written at entry | 88 | 15 + 60-75 |
| 20 | routes/adjustment_check.py:6; adjustment_check.py:33 | "type None -> source none and no results"; no generic playbook in code | design the generic set first, then ~60 | | design + 60 |
| 90 | adjustment_check.py:566-587 trigger_words; routes/adjustment_check.py:132 | raw id appears when the lookup returns None or the Flag has no cmp (`_condition` None) | catalogue line for day rules | into 57/59 | 20 |
| 12 | routes/adjustment_opportunities.py:136-140 `format(s.value,"f")`; routes/adjustment_check.py:90 `SHOWN_PLACES = 0.0001` | 4 decimals, no unit | 2 places + unit (fixture tests change) | with 88 | 30 |

## 2. Compare, approaches, paper orders, exits, history
| Item | Files | What exists | Smallest fix | Overlap | Min |
|---|---|---|---|---|---|
| 79/87 (ADR-272) | B/ofo_app/routes/adjustment.py:515-576, :624; adjustment_check.py:29 prices_fresh; F AdjustCompare.vue | reply has only `warnings`; no stale / "as of" text in AdjustCompare.vue; check already computes prices_fresh | reuse freshness; add stale_since/fresh; no leaders when stale; Vue disables Prepare + banner; Pause box / TrackingPanel read `withheld` (routes/adjustment_check.py:100) | 77, 91 | 90 |
| 91 | adjustment_readers.py:508-509; adjustment_check.py:214-219; approaches.py:644-650 | `market.now = ctx.clock()`; `_time_exit_due` refuses when `exits.hhmm < exits.time_exit` | unverified: code uses the clock; write a test of exit_inputs_of(guards, position, now) to find where 14:20 enters | with 79 | 30 (+ more if a bug) |
| 77 | adjustment_readers.py:499-569; adjustment.py:510-512 | one frozen held_read then judge_spot; no TTL found | "prices from hh:mm:ss" label; cause unmeasured | 79 | 20 |
| 15/52 (ADR-256) | F pages/StrategyBuilderPage.vue:411-428 reviewPending; lib/paperDrafts.js confirmRowsFor | exit edits legs then opens the confirm list; rows carry orders only | call outcome + margin routes on the after-exit legs; 2 lines + warning | | 90 |
| 43 (ADR-257) | B/ofo_app/paper_monitor.py:220-233; paper_trigger_store.py:27-28, 95-99; routes/paper.py; F PaperStops.vue | leg_stop fires `targets = [t.contract_id]`; no wing field | (checker: with_wing column + migration, 120) lead plan: add the same-type same-expiry bought leg as a second target at fire time, no migration | | 60-120 |
| 23 (ADR-255) | B/ofo/engine/adjust_history.py:227-231, :248, Step Literal :64 | `used = sum(1 for r in done if r.step == "adjustment")` | a step that leaves no open leg = "exit", not counted | flows into offered/compare T-18 | 45 |
| 80/30 (ADR-274) | routes/paper.py:726; freeze_read.py / freeze_store.py / checked_basket.py | one order per leg; no freeze in paper.py | group by (contract, side), sum, split at freeze qty | 84 same POST | 75 |
| 84/39 (ADR-273) | routes/adjustment_history.py:185-194 `_why`, :90; routes/paper.py:726; F StrategyBuilderPage.vue:445 | `_why` -> adjust_history_own_change without a suggestion; post carries preparedBasketLegs, no approach id | send approach_id + edited; store; third why case | 80 | 75 |
| ADR-261 | F AdjustDrawer.vue, StrategyBuilderPage.vue | not read | unverified | 42 | - |
| 68 (ADR-269) | approaches.py:531-545; routes/paper.py; paper store; confirm list | A-04 builds the later-expiry roll ("adjust_roll_out_no_next_expiry"); rolls stay inside one strategy; no link, no two-step confirm, no new strategy | mark the later-expiry roll "new strategy": post closes the old and creates a linked one | 23 | 300+ (lead: 240 reusing create + paper post) |
| 42 | F AdjustCompare.vue:216, 247-248, 264 | picked-only scope keeps only A-36 -> empty | if picked holds only A-36, default to 'all' | ADR-261 | 15 |
| 44 | paper_monitor.py:232; paper_store.py:34; routes/paper.py:150 | kind hard-coded "stop" | "cond_exit" for non-leg_stop kinds; REDUCING_KINDS; check DB kind constraint | 23 | 40 |
| 37 | routes/outcome.py:398, 906-910 | Booked read only for the target block | add booked to the at-expiry table when include_booked | | 40 |
| 32 | B/ofo/errors/templates.py:1372, 1375-1378 | "{leg} has fallen from {entry} to {now}"; "holds {lots} lots" | reword; plural-aware | | 15 |
| 35/85 | F lib/legEdit.js:167; tests leg-edit.test.js:853, 857 | quotes the strike | use the price | | 10 |
| 22, A-26 note | not located | | unverified | | - |

## 3. Builder, market data, catalogue, lists, settings
| Item | Files | What exists | Smallest fix | Overlap | Min |
|---|---|---|---|---|---|
| 47 (ADR-265) | B/ofo/outcome/planned_entry.py:31-41; routes/planned_entry.py:104; settings registry.json | LTP wins, mid only without LTP (reverse of ADR-265); `source` "ltp"/"mid" exists | mid first (bid and ask live), LTP fallback, setting, credit > width warning | 17; ADR-264 keys | 90 |
| 1 | B/ofo/instruments/catalogue.py:377-400 `_refuse_truncation` | per-index `gone*100 > limit*live` (:387), per-expiry `gone > 0.5*live` (:397); ignores where strikes vanished | pass when the survivors are one contiguous block (wing trim); log the refusal text | | 60 |
| 70 | B/ofo_app/feed_bus.py FeedRelay :416, status TTL 5 s :48; ofo/marketdata/feed_health.py:187 | market_closed_for falls back to the calendar without `.feed` | unverified suspect: after close the status lapses -> quotes UNAVAILABLE -> planning_price_usable (quote.py:38) rejects; keep the last close on the API side | 17 | 120 |
| 17 | same + ofo/outcome/service.py:876; ofo/engine/estimate.py:71 | engine raises "has no IV" with no usable price | after 70, use the paper table's price | 70 | 30 |
| 72/73 (ADR-271) | strategy_store.py:115-116; F lib/strategyActivity.js:112-114; MyStrategiesPage.vue; toast | paper orders (paper_book.py, migration 0028) not in the check; Undo inline | `AND NOT EXISTS (paper orders)`; reason text; Undo in the fixed toast | 25 | 75 |
| 25/71 (ADR-259) | MyStrategiesPage.vue:24, 46; store; StrategyBuilderPage.vue + lib/legEdit.js:23 NO_LEGS_YET | status only 'draft'; nothing marks completed | derive "completed" (all legs closed) in the list query; Completed page; reopen shows "All legs closed" + result | 72/73, 4 | 150 |
| 4 (ADR-263) | lib/paperDrafts.js:172-173; SummaryCards.vue; payoff table; outcome/serialize.py:98, 286 | max profit/loss after charges; profit/loss left + payoff table gross; no label | engine's after-charges figure + "(after charges)" | 25/71 | 120 |
| 83 (ADR-262) | B/ofo/strategy/placement.py:98-136; catalogue.yaml:110-122 | IC placed by steps (`params p, q default 2`) from listed_atm(spot); no delta, no preference | (checker 180) lead plan: placement mode by delta reusing approaches.py target-delta pick + user setting | ADR-264 | 90-180 |
| ADR-264 lock | B/ofo/settings/layers.py:125-140 resolve; registry.json; layered-key lists :48-55 | 3 layers (strategy, user, admin), no lock; 99 registry keys (lead count) | `locked` flag per key; resolve ignores user/strategy when locked; writers refuse | 47, 83 | 60 |
| 48 | StrategyBuilderPage.vue (no draft storage), lib/draftLink.js | only a `draft` query string seeds legs (:86-99); no sessionStorage | write legs to sessionStorage, read on mount | 82 | 60 |
| 82 | components/strategy/ReadyMadePanel.vue:157 | ErrorMessage after the cards, no Retry | next to the expiry box + Retry | 48 | 30 |
| 7/86 | SaveDraftBar.vue or PaperStrategies.vue (not opened) | unverified | loading line | | 30 |
| 2 | lib/legPicker.js or LegPicker.vue | unverified (formatter not found) | one OI formatter | | 15 |

## 4. Gate failures (full prepush 7 Nov 00:31-00:58 on b94c2484, TOTAL FAIL, 5 steps) and display/tooling
Gate (settings tree; logs C:\Users\itsab\AppData\Local\Temp\prepush-q277mvrd\):
| Failure | Cause | Fix | Min |
|---|---|---|---|
| ci_checks 06, 13 | knowledge/findings/rule-entry-baseline-taken-at-first-check.json has no `scope` (generic/project) | add scope | 5 |
| ci_checks 11, 17 | views/spec-digest.md stale | python tools/build_spec_digest.py . | 5 |
| coverage | ADR-255..274 have no stage in coverage-stages.yaml (20 rows) | add 20 stage rows | 15 |
| domain test_select_app_tests | tests/orchestrator/test_select_app_tests.py:60 PR241_SELECTION lacks tests_app/test_leg_edit_db_trips.py (added by 228b95a9) | add it with a why comment | 5 |
| domain test_money_outside_engine | StrategyBuilderPage.vue:143 `Number(id)`, :483 `showOrdersTick.value += 1` not in the frontend baseline | baseline with reason or remove the arithmetic | 10 |
| app test_openapi_drift | docs/api/openapi.json stale | python scripts/generate_openapi.py | 5 |
| frontend_unit strategy-table.test.js | LegList.vue:199 Math.abs; StrategyBuilderPage.vue:651 Math.max/min, :658 Math.sign/abs (from e34bd754); :143 Number( | move step maths into lib/legEdit.js or list the lines | 20 |
| frontend_unit strategy-live.test.js:228-232 | same :143 `Number(` | same fix | - |

Display / tooling (live tree):
| # | Files | What exists | Fix | Min |
|---|---|---|---|---|
| 41 | routes/paper.py:675-684, _figures :416-440 | `_totals` blanks the total on the first book with unbooked None ("never a partial sum", REQ-109 AC-5) | skip books with no open legs; summing around an unpriced OPEN book would be a SPEC CHANGE (owner) | 30 |
| 40 | routes/paper.py:654 `"position_count": len(figures["positions"])` | counts closed | open lots only | 10 |
| 28 | F lib/tracking.js:71 TRACKING_REFRESH_MS = 5000; usePaperRefresh.js:34 | 5 s poll; the "~3 s" not found | raise interval / one read | 15 |
| 55 | B/ofo_app/feed_bus.py:44 STREAM_MAXLEN = 20_000; :410, :523 | raw Kite frame per entry | lower to ~2000; reconnect log separate | 10 |
| 9 | F components/adjustments/SystemPlaybookAdmin.vue:58 `d.toLocaleString()` | browser locale | en-IN + Asia/Kolkata as PreferencesTab.vue:48 | 5 |
| 21 | F lib/displayFormat.js:57-59 | closed legs have no `lots` -> "65 units" | server sends lots on closed rows (no browser division, ADR-008) | 20 |
| 78 | B/ofo/errors/templates.py:1255 "Max profit not finite" | no zero branch | zero wording | 15 |
| 74 | tests_app/test_alert_gate_storage.py:221-228 | 0036 downgrade alone | downgrade from head / whole chain | 20 |
| 66 | B/ofo_app/config.py:46 DB_POOL_SIZE default 2 | | raise default (check db.py:64 pool_maximum vs role limit) | 10 |
| 62 | background.py:1462-1464 before_cycle, :1670 sync_frame | hook exists, cause not found | RCA first | - |
| 5, 8, 13, 14/75, 26, 46, 61 | not located | | locate first | - |
