# Lane D: the 32 deferred issues #724 to #755 (26-27 Nov 2026)

Step: clean-up D-07 (one triage pass on open issues), allowed beside any step of `docs/process/standing-direction.md`.
Branch `fix/deferred-1126` from `origin/integration/nb-1126` at 3d7aaf7. Paper only; no migration; no issue closed
here (the coordinator closes).

Spec basis: ADR-002, ADR-003, ADR-008 (one engine, exact money), ADR-016..019, ADR-237 (4), ADR-250, ADR-328 (3),
ADR-330 (3), (23), (34), (36); REQ-049, REQ-109, REQ-133 AC-3, REQ-138, REQ-154.

## Summary counts

| Class | Count | Issues |
|---|---|---|
| FIX NOW | 18 | #725 #726 #727 #728 #729 #732 #733 #734 #736 #737 #738 #739 #740 #743 #745 #746 #748 #749 |
| NEEDS THE OWNER | 0 | #732 answered: ADR-330 (44), option 1. #741: the coordinator read ADR-328 (3) as already answering it |
| NOT REPRODUCED | 1 | #741 (the order door refuses holding a contract both ways, code 438; guard test added) |
| WAITS FOR A STAGE | 4 | #735 #742 (D-12, after step 4), #750 #751 (step 4: sign-in, migration) |
| ALREADY FIXED | 2 | #747 (46b970e); #730 (the existing exit gate already refuses; regression test d41534f) |
| OTHER LANE NOW | 6 | #724 #744 #752 (Lane R), #753 (Lane J, carries the migrations), #754 #755 (Lane G) |
| NOT WORTH DOING | 1 | #731 |

Older `deferred` issues (135 open below #724): not triaged one by one in this pass; see "Older issues" below.

## Triage table

Harm: what a user loses. Size: small = one small push. Line numbers are on this branch at 3d7aaf7.

| # | What the user sees | Harm | Size | Class | Note |
|---|---|---|---|---|---|
| 724 | Builder leg list of a paper trade: the price now comes from the paper book (42b49f4), but the "as of" time next to it and the "Oldest leg price as of" line still come from the other (outcome) reply, so the time can belong to a different price | low | small | OTHER LANE NOW (Lane R) | Same reader class as #744 in `StrategyBuilderPage.vue`, where Lane R works today; remainder = `quoteAtById` / `oldest_quote_at` at `StrategyBuilderPage.vue:1257` |
| 725 | Paper P&L rows from the tracking reply: an open leg whose contract was closed and reopened shows only today's open part, not the part already booked | medium | small | FIX NOW | `routes/tracking.py:314` uses `.unbooked` for an open leg; ADR-328 (3) says the leg's total result. The panel's own rows read the book total since 42b49f4; the server row is still wrong for other readers |
| 726 | A tracking exit is stored with the time of the price quote; an exit from the orders screen is stored with the time it was placed, so History can show a tracking exit earlier than it happened | low | small | FIX NOW | `tracking.py:562` vs `paper.py:1388`; `paper_monitor.py:23` "never back-dated" |
| 727 | Exiting from the tracking panel when the price read fails shows a raw server error; the same failure on the orders screen shows a named "prices not live" refusal | medium | small | FIX NOW | `tracking.py:548` `on_read_error="raise"` |
| 728 | The two exit screens disagree on "not connected": one refuses when the broker link is down, the other goes on with what it has | low | small | FIX NOW | `paper_exit.py:64` `connected_rule`; one rule (provider status) for both, fail closed |
| 729 | An exit from the tracking panel closes only the lots read before the lock; if the leg grew in between, part of it stays open without a word | high | small | FIX NOW | `tracking.py:554`; `paper_exit` already supports `closes="locked"` |
| 730 | "Review and add" built on an old view of the trade could post an exit after the trade changed in another tab | none | - | ALREADY FIXED | The exit gate `usePaperExit({changed: paperContractsChanged})` already refuses Review and add and Confirm and closes an open dialog; regression test through the real book poll `frontend/tests/paper-dialog-contracts-changed-b6.test.js` (removing the gate: 2 red), d41534f |
| 731 | Two tabs can each send a partial exit of the same lot; both are stored | none | medium + migration | NOT WORTH DOING | The store locks the strategy and re-checks the open quantity under the lock (`paper_store.py:85-95,128-138`), so the two exits can never close more than is open; each is a legal order the user sent. An idempotency key needs a migration for no loss |
| 732 | A price-level exit does not fire while any of the trade's contracts has no live price, and nothing tells the user it is waiting | medium | medium | FIX NOW | Owner answer ADR-330 (44): one INFORMATIONAL alert per exit per day ("Your exit at 26,100 could not run: <contract> has no live price. It is still set."), the exit stays set, no order; through the one alert module; also covers ADR-330 (39) (index value too old) using the price reader's verdict |
| 733 | "Keep this level" re-arms a level that the index may already have crossed, so it fires on the next tick | low | medium | FIX NOW | Spec settled (found on the subject search, so not asked): ADR-317 (1) refuses a level already crossed at save time with the approved "Not saved: ..." wording; (2) no live price = kept; (7) "keeps it" is a save |
| 734 | A stop that fires in the first second after the watcher reloads can record "index value not available" in its alert | low | medium | FIX NOW | `paper_monitor.py` reload / `_fire`; alerts path, Tier A |
| 735 | internal: no user effect today. Four display price readers do not go through the one market reader | none | large | WAITS FOR A STAGE | Structural debt D-12 waits until step 4 is done |
| 736 | A deleted strategy's adjustment plan can still be read and changed, and its alerts styled | medium | small | FIX NOW | `playbook_store.py:329` `_OWNS_STRATEGY` lacks `deleted_at IS NULL`; `strategy_store._OWNED` has it |
| 737 | internal: a "not a number" price from the broker would pass into the execute checks instead of reading as no price | low | small | FIX NOW | `execute_plan.py:102`; money, Tier A |
| 738 | internal: a "not a number" or infinite strike or tick size in the instrument list would be stored | low | small | FIX NOW | `ofo/instruments/parser.py:52` |
| 739 | Outside India near midnight, "days left" to expiry on the Option Chain is one day off | low | small | FIX NOW | `displayFormat.js:144` `localDay`; one caller `useChainLive.js:155` |
| 740 | internal today (same holiday table): the stop watcher decides "market open" by its own rule, not the rule the rest of the app uses | low | small | FIX NOW | `paper_monitor.py:180` vs `may_act.market_open` |
| 741 | A trade with a buy and a sell leg of the same contract would show that contract's whole P&L on both rows | none found | - | NOT REPRODUCED | The tracking rows are one per contract (`book.contract_legs` over `net_positions`) and the order door refuses opening the held contract the other way (code 438, GC-TPD R-22), so two open rows of one contract cannot be stored; the review probe built it by hand. Guard `tests_app/test_tracking_rows_add_up_b5.py`: rows add up to the book total for an iron condor, a closed-and-reopened contract and a buy-then-sell (mutation `.total` -> `.unbooked`: 2 failed). Real gap found instead: a closed-and-reopened contract on the builder's Paper P&L panel shows the open lifecycle only (+65.00) and no closed row, so its rows do not add up to the book (+130.00); ADR-328 (3) + D-10 (the legs table shows the closed lifecycle as its own row) settle it: the panel adds the closed row. Recorded as a strict xfail; to build next |
| 742 | internal: 17 read-only routes count as reaching order code because of one import, so the order-closure guard protects nothing for them | none | medium | WAITS FOR A STAGE | Structural (D-12); the fix also changes guard pins, which need the owner's own words |
| 743 | When the daily alert cap or quiet time holds an alert, a price swinging across the higher step writes one "held" history row per candle for the rest of the day | medium | small | FIX NOW | `alert_gate.py:262-267` judges the hold on the step, not the rule's line; Tier A |
| 744 | Builder per-leg prices of a paper trade read other sources | - | - | OTHER LANE NOW (Lane R) | Full table and leg list fixed by 42b49f4; only `AdvancedDetails.vue:23` (bid/ask) left in the guard's REMAINING list |
| 745 | Create Strategy: a red "server took too long" box stays above a list that loaded fine | medium | small | FIX NOW | `CreateStrategyPage.vue:76-112` one shared error slot, cleared only at the start |
| 746 | When the database is busy, adopting a holding says the holding is wrong instead of "busy, nothing was changed" | medium | small | FIX NOW | `order_book_store.py:146-158`; `errors._busy_database_error` exists |
| 747 | Orderbook shows quantity in lots | - | - | ALREADY FIXED | 46b970e (on this branch): `tests_app/test_paper_order_lots.py`, `orderbook-columns-s25.test.js`; ready to close after the owner's re-test |
| 748 | Option Chain: after picking a new expiry, every price reads "Unavailable: no price has been received" for up to 26 s instead of "waiting for the first price" | medium | medium | FIX NOW | REQ-133 AC-3 gives the wording; catalogue `outcome_waiting_first_price` exists; `chain_push.py:415-418` |
| 749 | Builder closed-leg table: the stop-loss sentence wraps to 3 lines inside the narrow Exit column | low | small | FIX NOW | `ClosedRows.vue:14`; render as a full-width row |
| 750 | Builder Settings has only "Show legs as", and a choice is lost on reload | medium | large | WAITS FOR A STAGE | Step 4 (signed-in user, a settings table = migration) |
| 751 | An unsaved builder strategy is lost on reload | medium | large | WAITS FOR A STAGE | Step 4 (REQ-154, stored draft per user = migration) |
| 752 | After the close, prices keep moving under a 15:30 banner | - | - | OTHER LANE NOW (Lane R) | ADR-330 (36) built on fix/screen-findings-1126 (0e6f6ac, d73508f) |
| 753 | Editing a plan saved before ADR-247 silently adds the 2x-credit stop line to it | medium | medium | OTHER LANE NOW (Lane J) | Spec settled: ADR-250 (an old plan keeps its own stops, gains no 2x-credit line: "nothing under a live position changes without the user choosing it"), ADR-252 (23) (only a playbook switch is a new acceptance). Migration 0041's trigger restamps `accepted_at` on every body edit; the fix stamps it on a switch only = a trigger change = a migration. Real case: an edit of strategy 82's target (ADR-250's case) would add the 2x line |
| 754 | internal: an egress test is red when a proxy is set | - | - | OTHER LANE NOW (Lane G) | not touched |
| 755 | internal: the gate is red while a builder worktree sits under `.claude/worktrees/` | - | - | OTHER LANE NOW (Lane G) | not touched; this lane keeps helper worktrees outside the repo |

## Order of fixing (harm first, related ones in one push)

1. Push 1, backend exit and stores (Tier A): #729, #727, #725, #726, #728 (tracking exit door); #746, #736, #743, #740, #733,
   #737, #738.
2. Push 2, screens: #741, #745, #748, #749, #739, then #734 and #730 if time allows.

## Older issues

135 open `deferred` issues below #724 were not triaged one by one in this pass (budget). Small-looking candidates
from the titles alone, for a later pass: #602 (status time without a date), #614 ("exited 1 legs"), #710 (alert label
with no amount), #711 (raw instrument id on a trade page), #600, #597.

## Fixes

Highest status of every row: Fixed, not tested (by the owner in the browser). Tests named are red on the old code and
green on the new (runs recorded in the commits' lane reports; red runs for #737, #738, #740 re-run by the lane
session itself on the old source: 12 + 6 failed).

| # | Root cause (one sentence) | Class before -> after | Failing test first | Commit | Detection |
|---|---|---|---|---|---|
| 729 | The tracking exit closed the quantity read before the strategy lock, so lots added in between stayed open. | exit routes closing a pre-lock quantity: 1 -> 0 | `tests_app/test_strategy_tracking.py::test_a_leg_added_between_read_and_lock_tracking_route_closes_the_whole_locked_quantity` (closed 65, now 130) | 0dad97e | One-door guard `tests/test_paper_orders_one_door.py`: the tracking exit's side-flip exemption is gone, so a new signed-quantity build in a route goes red |
| 727 | The tracking exit let a failed price read raise (500); the orders route refused by name. | read-error behaviours: 2 -> 1 | `..._price_read_that_raises_is_409_prices_not_live_for_both_callers[tracking]` | 03336ac | the `on_read_error` parameter is removed: no caller can choose the 500 again |
| 728 | The two exit routes used two different "connected" rules. | connected rules: 2 -> 1 (provider status, fail closed) | `..._disconnected_provider_is_refused_not_connected_for_both_callers_and_nothing_is_stored[orders]` | 03336ac | `connected_rule` parameter removed |
| 726 | The tracking exit stored the quote's time as the order time. | exit paths back-dating: 1 -> 0 | `test_tracking_exit_order_time_is_the_answer_time_not_the_quote_time` | af25b2e | No detection change: one call site, pinned by the test |
| 725 | An open leg's row showed only the open part, dropping the part booked by an earlier closed lifecycle. | rows not the engine total: 1 -> 0 | `test_an_open_leg_bought_again_after_a_closed_lifecycle_shows_the_contracts_engine_total` (9672.00 -> 10972.00) | e7e37bc | No detection change: the figure is now the engine's `NetPosition.total`, no route arithmetic |
| 743 | A held alert episode was judged by the held step's band, not the rule's line. | hold checks by step: 1 -> 0 | `tests/adjustment/test_alert_gate_line_judged.py` (8 held events -> 1 episode) | 33f61c1 | No detection change: the record and hold paths now call the same `_line` |
| 746 | The order-book store turned every database error in its savepoint into "bad holding". | catch-all mappings hiding busy errors: 1 -> 0 | `tests_app/test_order_book_store.py` real lock wait, sqlstate 55P03 | 7348cb8 | `errors.busy_database_error` is public, one helper for every store |
| 736 | The playbook ownership check and plan read did not leave out deleted strategies. | owner queries without the filter (named): 2 -> 0; 13 more listed below to file | `tests_app/test_playbook_store.py` | 1ec0c35 | listed as a deferred issue to file |
| 737, 738 | Python's Decimal accepts NaN and Infinity, and four parsers of broker/file input did not refuse them. | parsers without a finite check: 4 -> 0 | `tests/instruments/test_parser_finite.py`, `tests_app/test_execute_plan_typed_entry.py`, `tests_app/test_kite_reads.py` | 0a605d6 | No detection change: the other money parsers were read and already check |
| 740 | The stop watcher decided "market open" with its own calendar call, not the app's one rule. | market-open rules: 2 -> 1 | `tests_app/test_paper_monitor.py::test_nothing_fires_while_the_market_is_closed[feed-closed]` | 9834d86 | the monitor's `holidays=` parameter is removed |
| 733 | "Keep this level" stored the exit again without the crossed-level test the Save route runs. | trigger store paths without it: 1 -> 0 | `tests_app/test_paper_triggers_routes.py` (200 -> 422) | 2044449 | Keep calls the save route's own `check_trigger_levels` |
| 732 | An exit blocked by a contract with no live price returned silently. | silent blocked exits: 1 -> 0 | `tests_app/test_paper_monitor.py`, `tests_app/test_actionable_alerts.py` (once a day) | 866768b | named rule `actionable_alerts.inform_once_per_day` |
| 734 | A stop firing before the first index tick after a reload recorded "not available". | fires without the index fallback: 1 -> 0 | `tests_app/test_paper_monitor.py` | (b4 commits) | No detection change: one fire path |
| 745 | Create Strategy kept one error slot for all its reads, cleared only at the start. | shared error slots: 1 -> 0 | `frontend/tests/create-strategy-d38.test.js` | 91a652e | No detection change: one page |
| 749 | The stop reason sat inside the narrow Exit cell. | - | `frontend/tests/closed-rows-d10.test.js` | a5f40c6 | No detection change: layout |
| 739 | `localDay` used the browser's calendar day. | browser-day readers: 1 -> 0 | `TZ=America/New_York npx vitest run tests/display-format.test.js` | d134b8d | No detection change: one function, one caller |
| 748 | A held contract with no first price was given the same "unavailable" word as an unknown one. | - | `tests_app/test_chain_live.py`, `frontend/tests/option-chain.test.js` | 3d40c82 | No detection change |

## Re-test in the browser (PC, 27 Nov)

- Re-test #729: during market hours open a paper iron condor's builder page; in a second tab add one more lot to one
  leg; in the first tab (not reloaded) press Exit on that leg in the Paper P&L panel and confirm. Expect: the Orderbook
  shows one exit order for the WHOLE quantity (2 lots), and the leg reads closed. Before: 1 lot stayed open.
- Re-test #727 / #728: with prices disconnected (Broker > Disconnect), press Exit on a leg in the Paper P&L panel and
  on the Orders screen. Expect: both show the same named "not connected" line and nothing is stored. Before: one of
  them went ahead or showed a server error.
- Re-test #726: exit a leg from the Paper P&L panel at, say, 10:15:30 and open the trade's History. Expect: the exit's
  time is 10:15:30 (when you pressed), not the earlier time of the last price.
- Re-test #725: on a paper trade, close one leg and then buy the same contract again; look at that leg's row on the
  Paper P&L panel. Expect: the row shows the same total as the legs table beside it (booked part included).
- Re-test #733: on the Stops panel, with an index exit marked "set before the last adjustment", wait until NIFTY is
  beyond that level and press Keep. Expect: "Not saved: the live price is already at or beyond this level, so this
  exit would close the trade straight away. To close now, use Exit." Nothing changes.
- Re-test #732: arm an index exit on a paper trade where one contract shows no live price (or after the close is not
  possible: needs market hours) and let NIFTY cross. Expect: one pop-up "Your exit at <level> could not run: <contract>
  has no live price. It is still set." and one History row; no second one that day; the exit is still listed as set.
- Re-test #745: Create Strategy > Guided > "I already know my strategy" > NIFTY. Expect: no red "took too long" box
  above a list that loaded. (A slow server is needed to see the old box; if it appears, it now names only the read
  that is still failing and goes when that read succeeds.)
- Re-test #749: open a paper trade with a leg closed by a stop-loss. Expect: the closed-leg table's stop-loss sentence
  sits on its own full-width line under the row, not squeezed into the Exit column.
- Re-test #748: Option Chain > NIFTY > pick a new expiry in market hours. Expect: while the first prices arrive the
  cells say "Waiting for the first live price", not "Unavailable: no price has been received".
- Re-test #739: only visible outside India time near midnight; no PC step (covered by the test above).
- Re-test #736: delete a strategy that has an adjustment plan, then open its plan link from History (or an old tab).
  Expect: "not found", not the plan.
- #737, #738, #740, #743, #746: no screen step that can be forced on demand; covered by the named tests.


## Push 2 (panel rows; #730)

| Item | Root cause | Class before -> after | Tests red -> green | Commits | Review |
|---|---|---|---|---|---|
| #741 follow-up: builder Paper P&L panel rows | The panel built its rows from the tracking reply (one row per contract, 5 s poll) and never showed the book's closed lifecycles, so a closed-and-reopened contract showed +65.00 with no closed row against a book total of +130.00; round 1's mix of tracking rows and book rows doubled an exit for one poll (135 vs 75). | panel row sources: tracking rows + book figures -> the book's own rows (open positions, then closed lifecycles) whenever the book read is this strategy's | `frontend/tests/panel-rows-closed-b6.test.js`: round 1 2 of 3 red; round 2 cases R2-1..R2-4 4 of 8 red on round 1, all green; mutation (old panel) 4 red | 85dee14, 34095da | Tier A Opus round 1 REVISE (1 major, 3 minor), round 2 PASS (5 minors below) |
| #730 | Not a defect: the existing exit gate (`usePaperExit({changed: paperContractsChanged})`) already refuses Review and add and Confirm, and closes an open dialog, when the open contracts changed. | - | `frontend/tests/paper-dialog-contracts-changed-b6.test.js` through the real book poll: 3 passed; removing `changed:` from the page: 2 red | d41534f (test only) | - |

Re-test #741 follow-up: on a paper trade, exit one leg, then buy the same contract again; open the builder's Paper P&L
panel. Expect: two rows for that contract, the closed one ("Exited at ...") and the open one, each with the same
figure as the legs table beside it, and the rows add up to the panel's total. Also right after pressing Exit on a leg:
that leg never shows twice.

Re-test #730: open the same paper trade in two tabs; in tab 2 exit a leg; in tab 1 (not reloaded) open "Review and
add" of another edit. Expect: the existing "changed elsewhere" line, and nothing is sent.

To file as deferred (round-2 review minors, rounds used up):
- panel: a failed read on a book with no open and no closed entry falls back to tracking rows without the dash
  (`TrackingPanel.vue:150`); a book with no `strategy_id` is accepted (`:126`; the server always sends it); a label
  from the tracking reply can show the pre-exit quantity for one poll (`:147-148`); `v-if="view.legs.length"` hides
  book rows when the tracking reply has no legs (`:14`, pre-existing); one-source-d41 test 5 no longer pins the label's
  source (`:123`).

Process note: the first prepush run failed in preflight on `tests_app/test_openapi_drift.py`: the fast pre-check
built the OpenAPI document but did not compare it with the committed one. Lane D's own two route changes (#733 keep,
#729 tracking exit) caused the drift; regenerated in 91cc43b. Lesson for briefs: "openapi check" means running
`tests_app/test_openapi_drift.py`, not only the generator.

## Tier A review (independent Opus, 26 Nov evening): PASS, 4 minors, all to file as deferred

- R1 (#726 + #729) `routes/tracking.py:549,570`: `placed_at` is the route's answer time, read before the price read
  (up to 3 s) and before the lock; an add committed in between is closed by an exit stamped earlier than it. Money is
  unaffected (the book replays by id); lists ordered by `placed_at` show the wrong order. Fix: stamp under the lock.
- R2 (#732) `paper_monitor.py:470-481`: the once-a-day mark is set before the write, so a failed write loses that
  day's message; a contract with no stored row raises in `_contract_text` (log only); a retired / delisted contract is
  told "It is still set" although it never comes back (needs its own wording: owner, against ADR-330 (44)).
- R3 (#734) `paper_monitor.py:494-496`: the up-to-1 s index read runs inside the fire's open DB transaction (no
  strategy lock held yet); keeps a connection idle in transaction. Fix: read the index before opening the session.
- R4 (#732) the exit-not-run row uses kind `stop_fired` (a new kind needs a migration: the kinds check constraint);
  no screen labels or counts it as "Stop fired" today; give it its own kind with the next migration.

## Ready to close (for the coordinator)

- #747: fixed by 46b970e (already on integration/nb-1126).
- After the owner's re-test: #725 #726 #727 #728 #729 #732 #733 #734 #736 #737 #738 #739 #740 #743 #745 #746 #748 #749 (each commit carries the issue number; no `Fixes` line was written, per the rule, since the owner's screen check is part of done). #741: close as not reproducible (guard added; the panel's closed-lifecycle rows are fixed in push 2). #730: close as already guarded (test added).

## To file as deferred issues

- The four Tier A minors R1-R4 above.
- #741 follow-up: the builder Paper P&L panel shows no closed-lifecycle row for a closed-and-reopened contract (strict xfail `test_reopened_contract_row_equals_the_legs_table_row`).
- The `ofo_test` catalogue leak between test files ("would drop 750 of 750" on the next file), seen by the tracking builder; not traced.
- Soft-deleted strategy still readable through 11 more `playbook_store.py` queries and `reconciliation_store._SHARED`, `scenario_guard._MARKER` (found while fixing #736; the two queries #736 names are fixed).
