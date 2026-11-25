# Results: one door per capability (modular clean-up)

Plan: `PLAN.md`. Owner questions: `owner-questions.md`. Branch `refactor/modular-doors`.

**Status (26 Nov night, Lane A, unattended run): Step 0, 0b, Phases 3, 4, 6, 7 DONE. Pushed: `a99730b8` (0b), `546c67d3`
(Phase 3), `87a446bf` (Phase 4); Phases 6 and 7 merged after it (push state: see the last commit on the branch). Phase 8
waits for the Lane B merge.** This file is written so a fresh session can carry on from it alone. Read
`PLAN-phases-3-8.md` for the build order and `PLAN.md` for the why.

| Phase | Scope | State | Where |
|---|---|---|---|
| 1 | B3 `read_market` + B5 `check_trigger_levels` (D-01, S-20, ADR-327) | DONE, pushed | `fce27095`, `58bd51d9`, `3b8ae9b7` |
| 2 | B4 `may_act` + F1 `priceState` (D-05 server half, D-39) | DONE, pushed | `707bc5d4`, `0e30edc1` |
| 3 | F3 + F5 + B6 one paper book source (D-41 (two readers), ADR-328 (3)) | DONE (review PASS) | `e5622280` tests, `42c1f467`..`491ca7e2` code, merged into the branch |
| 4 | B1 exit door + F2 exit gate (D-05, ADR-328 (4)) + R5 | DONE (Tier A Opus PASS; one fix round) | backend `81e0b561`..`e79857a2`, frontend `643f0bdd`, `440e0299`, `15fe3268`, fixes on `wt/phase4-fix` |
| 5 | F6 `useLegDoor` (D-60) | NOT STARTED | `PLAN.md` Phase 5, OQ-1 |
| 6 | B2 close list (real path), F7, F8; B7 not built | DONE (B2 Tier A Opus PASS; F7/F8 Sonnet PASS) | `8862b957`..`bc4d8df1`, merged |
| 7 | R2 `owns`, R3 browser, R1 comment; rest skipped/parked | DONE (Sonnet PASS) | `45fd9dfb`..`637ea5cc`, merged |
| 8 | Guard test with exemption list and allowlist | NOT STARTED | `PLAN.md` Phase 8 |

## Step 0: merge of fix/ic-live-test-1123

| Claim | Evidence |
|---|---|
| Merge | `4350f336` of `6574e475`; the fix branch's App tests CI was green (run 45645290337) |
| Conflicts | `coverage-stages.yaml` (all four rows ADR-326..329 kept, S6.7); `spec-digest.md` (regenerated); `coverage-register.md` (regenerated, 1035 rows) |
| Generated files | OpenAPI and reply inventory regenerate with no diff |
| vitest | 223 files, 2622 tests passed |
| pytest tests/errors + d57 + money scan | 721 passed |
| DB selection, base `b1055c5` | 218 of 218 files exit 0 on fresh clones (4089 passed, 1 skipped = `test_execute_replay_api` live-server test) |
| ci_local | TOTAL 16 passed, 0 failed, 5 skipped |

### Section 9 first commands

| Phase | First command | Result |
|---|---|---|
| Step 0 | vitest | green (agrees) |
| 3, 4 | run at phase start | tests not yet written |
| 5 | `leg-step-duplicate-d60` + `leg-duplicate-d60` | 36 passed (agrees) |
| 6 | `test_execute_route -k exit_legs` | 1 passed (agrees); `exit_legs` at `execute_plan.py:223-226` sorts `sorted(held.items())` |
| 7 | `test_strategy_alert_style` | 37 passed (agrees) |
| 8 | G1 AST scan | 34 sites by `file::function`, 44 calls in 17 files; all in plan-named files except the door itself (`market_read.py::_read`); exemptions must be keyed by `file::function` |

Verdict: no result contradicts any phase; no phase parked.

## Phase 1: B3 read_market + B5 trigger check (D-01, S-20, ADR-327)

**Door.** `backend/ofo_app/market_read.py`: `read_market(ctx, feed, underlying, leg_keys, need_index, purpose, *, wait)`
holds the legs (and the index) through `live_push.hold_and_read`, waits up to 3 s, and returns a state per price
(live / stale / missing / market_closed). `hold_and_read` gained optional `sleep` and `now` seams (loop defaults), so
tests never sleep. `check_trigger_levels` in `routes/paper.py` replaces `_already_crossed`: market closed saves; market
open with no context, a leg with no feed key, a failed read or no live price after the wait is refused with the new
template `paper_trigger_price_unreadable` (ADR-327); a live crossed price keeps `paper_trigger_already_crossed` /
`paper_trigger_leg_already_crossed`. The read runs before the strategy row lock; open legs are re-validated under it.

**Callers, before -> after.**
- Trigger save (`add_paper_triggers`): raw `read_snapshot`, no hold -> `read_market` (needs the `get_live_feed` and
  answer-clock dependencies).
- Monitor (S-20): `reload` held the index only for conditional exits -> holds the index for every armed trigger. No read
  in `_fire`.
- Manual exit price (`_server_exit_prices` via `tracking._snapshot`): unchanged, left for Phase 4 (it already holds the
  legs with its own loop; moving it changes the wait and the refusal mapping).

**Tests.** `tests_app/test_paper_trigger_unheld_index.py`: 22 (no DB); `test_paper_triggers_routes.py`: 65 (DB, incl. the
unheld-feed route twin); `test_paper_monitor.py`: 23 (DB, incl. S-20); `test_paper_order_door.py` (`market_read` added to
`PAPER_MODULES`); `tests/errors`: 710 (new template pin, "pending owner read").

**Commits.** `fce27095` tests (red), `58bd51d9` code (green), `3b8ae9b7` gates (ruff ratchet, ADR-327 coverage stage,
repo scans) and two review pins. **Review:** Tier A, Opus: PASS, no critical or major finding. Minors fixed in
`3b8ae9b7`: the production 3 s wait is pinned by a test, and a route twin test was added. **Prepush:** TOTAL PASS on
`3b8ae9b7`.

**Owner read (25 Nov evening, ADR-328 (5)): approved, mark cleared.** Before that: the error template `paper_trigger_price_unreadable` (STRATEGY_VALIDATION_446, pin in
`tests/errors/template_pins.json`): only its first sentence ("Not saved: the live price could not be read, so this level
cannot be checked. Try again in a moment.") is ADR-327's. Its impact and next-action lines are builder wording and need the
owner's read (open question 3 below).

**Deferred.**
- The Keep-this-level route (`keep_paper_trigger`) has no price check (review finding 4; ADR-317 treats it as low risk).
- The first-second S-20 race (review finding 3): a fire in the first second after `reload`, before the index tick
  arrives, can still record "not available".
- Display and advisory readers not moved: `routes/outcome.py:1263`, `live_push.py:170`, `chain_push.py:305`,
  `index_push.py:84` (they would add up to 3 s waits).
- Manual exit price read: Phase 4.

## Phase 2: B4 may_act + F1 priceState (D-05 server half, D-39 where same rule)

**Door, server.** `backend/ofo_app/may_act.py`: `may_act(ctx, action, at, prices=None) -> Allowed | Refused(reason, failure)`,
actions `place`, `exit`, `set_trigger`. Market half (`market_open`, the one `market_state` answer, no context fails
closed) then price half (`prices_ok`: every state must be `live`; stale, missing and unknown are not live). Refusal codes
and failures are the ones the routes raised before: `gate_market_closed` (CONFLICT), `tracking_exit_prices_not_live`
(CONFLICT), `paper_trigger_price_unreadable` (no failure). `set_trigger` with the market closed is Allowed with
`market_open=False` (ADR-327 (3): saved, arms at the next live tick). Server-only; no endpoint. Added to `PAPER_MODULES`.

**Callers, before -> after.** 7 separate "may this act" decisions -> 1 door + 0 copies of those 7:
- `paper_limit.refuse_when_closed` (function removed) and its 3 callers: `place_checked`, the orders route
  (`routes/paper.py`), the tracking exit route (`routes/tracking.py`) -> `may_act.refuse_unless_allowed` (`place`; `exit`).
- `check_trigger_levels` market-closed test (`market_state(...).closed`) -> `may_act.market_open`.
- `market_read.read_market` market-closed test -> `may_act.market_open`.
- `_server_exit_prices` final "every leg live" check -> `may_act.prices_ok("exit", ...)` (a price with no number reads
  as missing, as before).
- `_judge_levels` "price not live -> unreadable" -> `may_act.prices_ok("set_trigger", ...)`; the crossed-before-unreadable
  order is unchanged. The literal `paper_trigger_price_unreadable` now lives once (`may_act`), `routes/paper.py` aliases it.

**Left, with the reason.**
- `paper_monitor.on_quote` (`is_market_open(now, self._holidays)`): its own injected holidays and the feed clock; the
  door asks the provider's feed state (`market_closed_for`), whose default calendar has no holidays. Not provably the
  same answer, so not moved (the monitor's fire path is Phase 4).
- `paper_monitor` `paper.is_live` at `:259`, `:273`: the price a fire is recorded with (missing: stays armed, NotYet) -
  Phase 4 `exit_strategy`.
- `routes/tracking.py` `paper.exit_prices_now` raising `PricesNotLive`: domain-layer raise with the same code; Phase 4.
- `adjustment_readers.py:854` `paper.is_live`: display prices, not an act gate.
- `paper_settlement.py:223` `is_market_open` at midday: "is that day a trading day", a different question.
- `routes/outcome.market_state` is the source the door uses; its display callers (`chain_push`, `index_push`,
  `leg_picker`, `indices`, `planned_entry`, `outcome`) answer "what to show", not "may it act".
- `ofo/execution/safety.py` market-open gate: the real-order path, out of scope (ADR-281).

**Door, screen.** `frontend/src/lib/priceState.js`: `priceState({readFailed, held, serverState, closedText})` ->
`live | stale | missing | closed | read_failed` and `usePriceFreshness` -> `{state, live, readFailed, readOk, exitReason}`.
`readOk` is the Positions rule (`listIsStale`, D-05); the builder's `paperReadFailed` goes through it
(`StrategyBuilderPage.vue`: `paperBookFailed`), and `readOk` / `exitReason` are ready for the Phase 4 Exit gate (NOT wired:
no Exit button changed).

**Merged (same rule, same text, no visible change).**
- `NOT_CONNECTED_TEXT` (`tracking.js`) and `PAPER_NOT_CONNECTED` (`paperList.js`): one constant.
- `PAPER_PAUSED` (`paperList.js`, also `paperPnl.js`, `PaperStrategies.vue`) and the base of `pausedText` (`tracking.js`):
  one constant `PAUSED_TEXT`; `pausedText` is one function. `withAsOf` stays (it leaves the bare sentence without a time,
  `pausedText` says "not available": different results).
- `listIsStale` (one definition; `paperList.js` re-exports it); used by `PaperStrategies.vue` and `paperPnl.js` through
  `usePriceFreshness`.
- `NOT_LIVE_EXIT` (was local to `PaperStrategies.vue`) moved to `priceState.js`, ready for the builder gate.
- "Book is paused or not connected" (`state === 'PAUSED' || 'NOT_CONNECTED'`, twice: `tracking.js` `sharedTotal`,
  `PaperBookPanel.vue`) -> `bookNotLive`.

**Left, with the reason (different rule or different words; merging would change visible text).**
`UNREADABLE_TEXT` (`tracking.js`) vs `PAPER_BOOK_UNREADABLE` (`paperDrafts.js`): different wording. `NO_TOTAL`
(`PaperStrategies.vue:188`): the same rule in other words, kept as shown. `legPicker.js:7` `NOT_CONNECTED_LABEL` (a draft,
mirrors a backend constant) and `:100` `LIST_REASON_TEXT` (the server's reason map), `CreateStrategyPage.vue:25`
`NOT_PRICED`, `useChainLive.js:14` `NOT_LIVE_LABEL`, `IndexStrip.vue:15` "Index values are not live.": other surfaces,
other sentences. `sharedStateText.js` `RECONNECTING_PREFIX` and the builder `pricesStamp`: socket state, not the book
read. `paperDrafts.js` `confirmRowsFor` per-leg `price_state === 'live'`: a per-leg rule. `SummaryCards.vue:160`: D-39
basis prop, not a freshness string (not changed here).

**Tests.** `tests_app/test_may_act.py`: 19 (no DB; per state open+live, open+stale, open+missing, closed, session-edge
parity with `market_state` at 09:14, 09:15, 15:29, 15:30, 15:44, 15:45); `frontend/tests/priceState.test.js`: 17 (live,
stale, missing, closed, read failed, wording identity). Callers' existing tests unmodified and green (DB: paper routes,
server exit price, adjustment limit, save paths, batch buys first, triggers routes, builder after hours, duplicate leg,
tracking, tracking list, IC exits, monitor); whole vitest suite green. One pin updated:
`tests/orchestrator/test_select_app_tests.py` PR241_SELECTION gains the new test file (it imports modules that diff changes).

**Not wired yet.** `readOk` / `exitReason` (`usePriceFreshness`) and `NOT_LIVE_EXIT` are ready for the Phase 4 Exit gate;
no Exit button changed in Phase 2.

**Commits.** `707bc5d4` tests (red), `0e30edc1` code (green). **Review:** Tier B, Sonnet: PASS, no critical or major
finding. **Prepush:** TOTAL PASS on `0e30edc1`.

## Phase 3: one paper book source (F3 + F5 + B6), D-41 (two readers), ADR-328 (3): DONE

Built on `wt/phase3-a` from `4350f336`, merged with `--no-ff`. The patch `phase3-wip.patch.txt` was reused only for the
hunks plan 5.3 names; its join (by `instrument_id`), fixture and RESULTS hunk were dropped.

**Door, server.** `backend/ofo_app/strategy_money.py`: `live_prices(prices)`, `MoneyView`,
`strategy_money_view(orders, prices, *, totals_priced=True)`. Five copies of "price answers -> live map -> engine"
(`routes/paper.py` `_figures`, `_extremes`, `_after`; `routes/tracking.py` `_book_figures`;
`routes/adjustment_history.py` live map) -> 1 door. `TrackingLegOut` gains `contract_id: int`
(`int(held.instrument_id)`), additive; OpenAPI +5 lines and reply inventory +2 lines, exactly that field.

**Door, screen.** `usePaperBookRead.js`: `legPricesOf(book)` (contract-id text -> `{ltp, at, total, noPrice}`, open
legs only) and `paperPnlBlock(book, failed)`. `TrackingPanel.vue` `rows`: an open leg found by `contractId` takes price,
quote time and P&L together from the book; an exited leg, a leg the book does not hold, or a missing contract id keeps
the tracking row. `StrategyBuilderPage.vue` `paperTotal` from `paperPnlBlock`.

**Deviations from the plan (recorded).** `MoneyView.book` is lazy too, not only `by_contract` (the list route needs only
`lifecycle()`; counting test: 0 engine calls on construction, 1 with live totals, 2 with `totals_priced=False`).
Signature `(orders, prices, ...)`, not PLAN's `(strategy_id, prices)` (callers hold the orders; pinned `_figures`
signature). `LegPrice` is a plain object, not a component (a component would change pinned markup). Two polls remain
(book and tracking); there is one SOURCE for the leg price, not one poll. The patch's import reorder in `paper.py` was
not taken (the I001 finding predates it; ruff counts per file unchanged).

**Visible changes (screen-check list rows 3).** After hours the panel rows show the book's last close and its time
(ADR-212) instead of `-`. A partly exited leg shows its TOTAL (booked + open), the same as the table (ADR-328 (3)): in
test 13, `25.00` not `+20.00`. Right after an exit, for up to 5 s, one row may still show the tracking price or
"Exited at" while the other read catches up (two timers, by design).

**Tests.** `frontend/tests/one-source-d41.test.js`: 15 rows (13 red of 37 with `tracking.test.js` on the old code;
rows 4, 9, 10, 12 pin unchanged behaviour and are green on both); `tracking.test.js`: one new `it`;
`tests_app/test_strategy_money_view.py`: 19 (no DB).

| Claim | Evidence (command, result line) |
|---|---|
| Red first | `npx vitest run tests/one-source-d41.test.js tests/tracking.test.js`: `Tests 13 failed / 24 passed (37)` (`legPricesOf is not a function`, `150.95` vs `149.70`); pytest: `ImportError: cannot import name 'strategy_money'` |
| Whole vitest green | `npx vitest run`: `Test Files 224 passed (224)`, `Tests 2639 passed (2639)` |
| Python guards | `pytest tests/errors tests/test_money_outside_engine.py tests/orchestrator -q`: `1407 passed` |
| DB selection (base `4350f336`) | 50 files, each on a fresh clone via `/root/ofo-fresh-run.sh`: 50 of 50 exit 0, 928 passed |
| ci_local | `TOTAL: 16 passed, 0 failed, 5 skipped (118.4s)` |
| Old vs new money | reviewer probe: 3000 random books x live/missing/stale/None prices, old inline code vs door: 0 differences |
| Review | Sonnet, adversarial, fresh: PASS, no critical or major |

**Review minors (not fixed; listed).** M1: two tracking legs of one contract (a buy and a sell, REQ-030 AC-11) each show
the contract's whole net figure, so the rows sum to twice the book total. Not new: the old code also indexed one figure
per contract (`by_id[leg.instrument_id]`). Deferred issue (plan section 6, row 21). M2: `legPricesOf` keys a position
with a null `contract_id` as the text "null" (only a contrived tracking id could match). M3: test 7's fixture sends
`price_state 'stale'` with an `ltp_text`; the real after-hours reply sends `live` with the last close (the panel ignores
`price_state`, so the assertion still holds).

## Phase 4: the exit door (B1 + F2), D-05 builder half, ADR-328 (4), R5: DONE

Built in two parallel worktrees from the Phase 3 head `491ca7e2` (backend `wt/phase4-be`, frontend `wt/phase4-fe`;
file-disjoint), merged with `--no-ff` (`b567a156`), then one review-fix round (`wt/phase4-fix`).

**Door, server.** `backend/ofo/tracking/closing.py` (`Close`, `open_legs_to_close`, stdlib only) and
`backend/ofo_app/paper_exit.py` (`live_exit_prices`, `exit_strategy` -> `Exited` / `Refused` / `NotYet` / `Flat`).
Callers: tracking exit route, the orders route's `_server_exit_prices` and `paper_exit_risk` (both through the one read;
`_server_exit_prices` stays as a thin index-to-price adapter), the monitor `_fire`, settlement. Server exit builders:
3 + 1 pricer (+ the second `paper_exit_risk` caller) -> 1 door. R5: `ofo/engine/legs.py` `intrinsic_value`;
`paper_settlement.settle_price` deleted. `ofo/execution/**`, `routes/execute.py`, `execute_plan.py`: no diff.

**A3 deadlock: PROVEN and fixed.** Row 11 `[before_place]` on the pre-phase code: `asyncpg.exceptions.DeadlockDetectedError:
deadlock detected` (monitor claimed the trigger row, then waited for the strategy lock held by the tracking route, whose
`reconcile_triggers` waited for the trigger row). After the door (strategy lock first in every caller): one set of
closing rows, the loser stores nothing, no deadlock. Re-run independently by the Tier A reviewer on both trees.

**Goldens.** Rows 1-7 (tracking all / one, manual all / partial, conditional, leg stop, settlement of a two-expiry trade)
captured on the pre-phase code and pasted as literals; equal on both trees (contract, side, qty, Decimal price, kind,
reason, trigger, placed_at).

**Race-only change (5.4.3).** The monitor reads the net under the lock: a lot added between its first look and the lock
is closed in full (130, not 65; row 12b). The tracking route keeps its pre-read quantities (golden part-close of 65).

**Deviations (accepted by the Tier A review).** `live_exit_prices` does not run the market half of `may_act` (routes keep
`refuse_unless_allowed`, so the refusal order is unchanged); it takes feed keys and returns `paper.Price` per key (the
tracking route needs each leg's quote time). `exit_strategy` `prices` is a mapping read before the lock; `only` may be a
function of the locked net (`sorted` for the conditional exit, today's contract-id order); `placed_at` / `reason` may be
per-key mappings. Row 8 "one named leg stale" became "a stale price refuses the whole exit" plus (fix round) a mixed
stale/live case. `paper_exit_exceeds_open` is 422, as today. Correction of a builder claim: a monitor on a strategy with
no orders still raises `ValueError` in its unchanged pre-read (`paper_monitor.py` `net_positions` before the lock), so
there is no behaviour change; the door's empty-book `Flat` is reachable only in a race.

**Screen (F2 + ADR-328 (4)).** `priceState.js` `CHANGED_ELSEWHERE_EXIT` (ADR text verbatim), `usePaperExit.js`,
`ExitButton.vue`; `PaperBookPanel.vue`, `StrategyBuilderPage.vue`, `PaperStrategies.vue` (POST through `addToPaper`, body
exactly `{ orders }`). On a failed book read in the builder: Exit all and every per-leg Exit disabled, "Prices are not
live; try again when they update", Total / Avg / LTP / Booked / Unbooked / P&L show "—" (the Positions rule); an open Exit
dialog closes. While the trade changed elsewhere: both disabled with "This trade changed elsewhere. Reload to see the
current legs." (figures stay); an open Exit dialog closes and posts nothing; the Exit's kept edits cannot be posted
through "Review and add" either (fix round, Tier A minor 1). The reason line shows once, under Exit all.

**Tests changed under the plan's bound (section 1, "a test that pins a named bug").** `paper-place-refresh.test.js:231`
(ADR-328 (4)); `paper-book-live.test.js`, `one-read-u130f.test.js`, `one-source-d41.test.js` test 8 (D-05: a failed
read shows dashes in the builder panel, plan 5.4.2), commit `15fe3268` with old and new assertions per file.

| Claim | Evidence (command, result line) |
|---|---|
| Deadlock red before, green after | `/root/ofo-fresh-run.sh tests_app/test_exit_door.py` on the pre-phase tree: `3 failed, 29 passed` (deadlock[before_place] DeadlockDetectedError; 12b monitor race; old settle_price gone); on `b567a156`: `32 passed` |
| No real-path change | `git diff 546c67d3..b567a156 -- backend/ofo/execution backend/ofo_app/routes/execute.py backend/ofo_app/execute_plan.py \| wc -l`: `0` |
| R5 parity | reviewer script, CE/PE/FUT in/at/out: 9 of 9 equal |
| Backend DB selection (base `491ca7e2`) | 160 of 160 files exit 0 on fresh clones |
| Merged vitest | `npx vitest run` on `b567a156`: `Test Files 225 passed`, `Tests 2653 passed` |
| ci_local on `b567a156` | `TOTAL: 16 passed, 0 failed, 5 skipped` |
| Python guards | `pytest tests/errors tests/test_money_outside_engine.py tests/orchestrator tests/tracking tests/engine`: `2556 passed, 1 skipped` |
| Review | Tier A, fresh Opus, adversarial (A1-A15): PASS, no critical or major; 6 minors, 1-4 and 6 fixed in the fix round |

**CI.** GitHub workflows run only on `pull_request` or a push to `main`; there is no PR tonight (owner bound), so the
gate is the local mirror: ci_local, the whole vitest suite, the `select_app_tests` DB run on fresh clones and prepush
(coordinator, 26 Nov 00:50 IST). The same holds for every phase of this night.

## Phase 6: B2 close list (real path), F7, F8; B7 not built: DONE

Built on `wt/phase6-a` from the Phase 4 merge `b567a156` (in parallel with Phase 7; file-disjoint), merged `--no-ff`.

- **B2.** `execute_plan.exit_legs` = `[LegToPrice(instrument_of(c.key), Action(c.side), c.quantity, None) for c in
  open_legs_to_close(dict(sorted(held.items())))]`; one new import (stdlib-only `ofo.tracking.closing`); `sorted` kept at
  the call site. `ofo/execution/**` and `routes/execute.py`: no diff. Oracle `tests_app/test_exit_legs_oracle.py` (the old
  body copied character for character; "NFO-OPT:10" vs "NFO-OPT:9" order trap, zero nets, shorts, condors): green on both
  trees. Basket golden `tests_app/test_exit_basket_golden.py`: the whole `KiteBasket` repr captured on the old code through
  the real `_wanted` -> `price_legs` -> `checked_basket` with a replayed margin reply (no `/orders` call); the reviewer's
  mutations (reversed order, flipped side, doubled qty) are all caught. Contract change pinned (review minor): a non-int net
  (Decimal, bool, float) now raises `TypeError` where the old body accepted it; unreachable (the only caller's
  `held_units` passes plain int, `execution_plan_store.py:374`, `order_book_store.py:78-79`) and fails closed before
  pricing (`bc4d8df1`).
- **F7.** `frontend/src/lib/paperTriggers.js` (`triggersPath`, `triggerListOf`, `armedIndexExits`); `PaperStops.vue` and
  `TrackingPanel.vue` script only, each keeps its failure policy and timing.
- **F8.** `MyStrategiesPage.vue` passes `null`; `renameStrategy` does the same revision read (one GET, one PATCH).
- **B7: not built (evidence).** Each writer has one caller: `add_alert` <- `paper_monitor.py:246`; `open_suggestion` <-
  `background.py:809`; `notifier.notify` <- `worker_watch.py:153`; different stores and transactions. Guard G4 (Phase 8)
  pins them.

| Claim | Evidence |
|---|---|
| Red first | `npx vitest run tests/paper-triggers-lib.test.js`: `Failed to resolve import "@/lib/paperTriggers"` |
| Oracle + golden + checked basket | `pytest tests_app/test_exit_legs_oracle.py tests_app/test_exit_basket_golden.py tests_app/test_checked_basket.py`: `30 passed` |
| Real-path tests unmodified, green | test_execute_route `31 passed`, test_exit_adopted_313b `9 passed`, tests/execution close_slices/close_refusals/partial `41 passed` (reviewer) |
| vitest / DB / ci_local on the worktree | 226 files / 2656 tests; DB selection base `b567a156` 45 of 45 exit 0; `TOTAL: 16 passed, 0 failed` |
| Review | B2: Tier A, fresh Opus: PASS (1 minor, pinned). F7/F8: Sonnet: PASS, no finding |

## Phase 7: helpers: DONE

Built on `wt/phase7-a` from `b567a156`, merged `--no-ff`.

| Item | Verdict | Reason / where |
|---|---|---|
| R1 cut-offs | KEEP, documented | comment block in `ofo/timeutil.py`: 15:30 valuation, 15:39 reconciliation, 15:45 paper settlement (REQ-109 AC-7); no code line |
| R2 ownership | DONE | `strategy_store.owns`; the 5 stores call it and keep their own errors (PauseNotFound, WatchNotFound, StyleNotFound, `real_book` None, PlanStoreError NOT_FOUND); `_OWNED_MANY` and `playbook_store` stay (other shapes) |
| R3 browser | DONE | `groupedIndian` exported, `tracking.js` imports it, `groupIndian` deleted (reviewer probe: 103 inputs, 0 differences) |
| R3 server | PARK | visible wording, template pins |
| R4 | SKIP | fail-closed vs default differ |
| R5 | DONE in Phase 4 | |
| R6, R8, R9 | PARK | real-order / broker path |
| R7 | SKIP | six copies with different errors; NaN gap is deferred row 18 |
| R10 | DONE before this plan | D-57 |
| R11, R12 | SKIP | two copies patched by tests; different inputs |

Deviation: `tests_app/test_order_closure_all_routes.py` pins two more route edges (`routes.level_watch`,
`routes.monitoring_pause` now reach the plan modules through `strategy_store`'s lazy imports), `PINNED_EDGE_COUNT` 37 -> 41
(`637ea5cc`). Review: the same `STRATEGY_STORE` set nine routes already carry; no new edge to `routes.execute`, the
execution return or any broker module. Tests: `test_strategy_owns.py` 6, `grouped-indian.test.js` 5,
`tests/test_ownership_sql_one_home.py` 2 (a planted copy fails it). Gates on the worktree: vitest 226 / 2658; DB selection
155 of 155 after the pin fix; ci_local 0 failed; ruff ratchet OK. Review: Sonnet: PASS (2 optional minors: no locked-read
caller of `owns` exists; the text guard matches the exact bind names).

## Phase 8: not started (waits for the Lane B merge)




## Next step (exact)

Superseded on 25 Nov evening. Build from `PLAN-phases-3-8.md` (code-verified plan for phases 3 to 8, with the owner's
ADR-328 answers, the two lanes and the ownership table):

1. Step 0 (section 4 of that file): merge `origin/fix/ic-live-test-1123` (head `6574e47` or newer, CI green) into
   `refactor/modular-doors`; resolve `coverage-stages.yaml` and `views/spec-digest.md`; regenerate; run the checks.
2. Step 0b: the ADR-328 spec notes in ADR-319 and REQ-109; push; CI green; cut Lane B (`refactor/leg-door`).
3. Lane A: Phase 3 (resume the patch only as section 5.3 says; its join key is wrong), 4, 6, 7, merge Lane B, 8.
   Lane B: Phase 5 only.
4. The owner screen-tests `refactor/modular-doors` once Step 0b is green (section 8 of that file).

## Screen-check list so far (click by click), for what is fixed

- **D-01 (Phase 1).** Positions > Paper > Stops > Conditional exit. Choose "Above a level the index is already beyond",
  in market hours, Save: "Not saved: the live price is already at or beyond this level ..." (the already-crossed text).
  With the price feed stopped (market hours), Save: "Not saved: the live price could not be read, so this level cannot be
  checked. Try again in a moment." With the market closed, Save: saved (arms at the next live tick).
- **S-20 (Phase 1).** Arm only a leg stop (no conditional exit) on a paper strategy in market hours, let it fire: the
  alert carries the NIFTY value, not "not available".
- **D-05, D-41, D-60:** not fixed yet (Phases 3-5). Once Phase 3 lands: the builder's Net Positions table and the Paper
  P&L panel show the same LTP per leg, the leg P&L rows add up to the before-charges total; after hours the panel rows
  show the last close.

## Re-test list (screens touched so far)

- Positions > Paper > Stops (trigger save).
- Paper alerts for leg stops.
- Paper exit from Positions (the market-closed refusal path now goes through `may_act`).
- Builder paper panels (`paperBookFailed` rename, no visible change).
- Every place showing "Paper P&L paused - prices not live" or the not-connected text (constants merged, no text change).
- With Phase 3 resumed: builder Net Positions and Paper P&L panel, and the after-hours panel rows.

## Gate notes for the next session

- Run python gates with the proxy variables unset: `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy -u http_proxy
  -u ALL_PROXY -u all_proxy python tools/ci_local.py`.
- Prepush takes about 31-33 minutes per head, and a hook refuses a push without it.
- Known guard traps: the money-outside-engine scan flags `+` in new backend files; the settings-reader guard;
  line-pinned exceptions in `paper_monitor.py`; the `tests/orchestrator/test_select_app_tests.py` PR241 selection set
  (new test files that import changed modules); `PAPER_MODULES` in `tests_app/test_paper_order_door.py` (add every new
  paper module).
- Hooks refuse `git worktree remove --force`, `git stash` in a worktree and `git reset --hard`; commit scratch changes in
  the throwaway worktree, then run a plain `git worktree remove`.
- `/root/ofo-dbtest.sh` and `/root/ofo-db-start.sh` are machine-local and gone on a new container: set up the test
  database per `docs/process/GC-ICLIVE-cloud-setup.md` section 1 (a template clone needs
  `revoke all on database <clone> from public`). DB tests run one file at a time (see CLAUDE.md).

## Open owner questions

Answered or closed on 25 Nov evening (see `owner-questions.md`): OQ-1 by ADR-328 (1), OQ-2 closed (keep the route),
3 by ADR-328 (5), OQ-4 by ADR-329 (unsaved builder legs kept for the chain trip; leaving elsewhere asks).

1. **OQ-1 D-60 (opposite-action step).** Should a strike step or move that lands on a held contract of the OPPOSITE action
   ask Increase / Keep separate / Cancel? Spec basis: REQ-030 AC-11; ADR-319 (1) and (4); the spec is silent on a step as
   distinct from a deliberate add. Recommendation: yes for a step or move, no question for a deliberate add (picker,
   ready-made), since two opposite rows on one contract net to nothing. Built meanwhile: ADR-319 (4) as written, no
   question for opposite action.
2. **OQ-2 `POST /strategies/{id}/tracking/exit`.** No frontend caller, four test files use it. Recommendation: keep it for
   now, moved onto the B1 exit door with behaviour unchanged (closes from the entry legs); delete in a later round with its
   tests moved onto the Positions exit route. Built meanwhile: kept and moved (Phase 4).
3. **Wording of `paper_trigger_price_unreadable` (STRATEGY_VALIDATION_446).** Only the first sentence is ADR-327's; the
   impact and next-action lines are builder wording and need the owner's read before they are final.
