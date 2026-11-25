# Results: one door per capability (modular clean-up)

Plan: `PLAN.md`. Branch `refactor/modular-doors`. Updated per phase.

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

**Commits.** `fce27095` tests (red), `58bd51d9` code (green), then the gates commit (ruff ratchet, ADR-327 coverage
stage, repo scans, two review test pins). Tier A review (Opus): PASS.

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

**Commits.** `707bc5d4` tests (red), then the code commit (see `git log`).

## Phase 3..8: not started
