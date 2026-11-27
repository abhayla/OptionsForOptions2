STATUS 23:20 | item 1, 1b: pushed (gate PASS) | item 2: gate running | 3: skipped (CONFLICT) | 4: for lane J2 | next push 23:40 | blocker: none (send_message to parent refused: untrusted device; this line is the report)

CONFLICT: tests/orchestrator/test_select_app_tests.py between feat/page-handovers-1127 and fix/last-close-1127 (item 3 merge aborted; the same merge also conflicts in LiveStrategyCard.vue, LiveStrategiesPage.vue, StrategyBuilderPage.vue, which Lane N's branch rewrote). Item 3 skipped.
CONFLICT: backend/ofo_app/routes/plan_watch.py between feat/page-handovers-1127 and hotfix/plan-watch-load-1127 (merge aborted; I took only the new file `frontend/src/lib/planWatchQueue.js` from it).
CONFLICT: tests_app/test_paper_order_lots_limit.py between feat/plan-door-1127 and hotfix/worker-join-1127 (both add the file). Whole J2 merge aborted; I took only `backend/ofo_app/monitoring_state.py` from J2. J2's own test file `tests_app/test_monitoring_state.py` NOT taken (3 of its tests need J2's `background.py`). Lane J2's worker half must be merged by the coordinator for the badge to ever read "active".

# Lane Y RESULTS (27 Nov 2026)

## Item 1: "Monitoring paused" on screen
- Route `GET /api/monitoring-state` (`backend/ofo_app/routes/monitoring_status.py`): one answer per Running trade of the user, from `monitoring_state.read_states` (the only computation). Fields: status, reason code, badge_text, health_text, reason_text, since_at, since_text. No bus (in-process feed) = every trade paused, `workers_down`.
- Heartbeat older than 2 minutes, unreadable store, trade not named by the worker snapshot: paused, "Not being watched: ...". Unknown status or reason: paused (fail closed).
- Page: `MonitoringBadge.vue` + `lib/monitoringState.js` (one read, 30 s refresh): Live Strategies card (server badge replaces the card's local one), Positions row, builder of a trade with a paper book. A failed read or an unnamed id prints "Monitoring paused" + "Health unknown".
- Core proof (before page code): `tests_app/test_monitoring_status_route.py::test_core_no_worker_record_for_two_minutes_reads_paused_with_a_reason` failed on a missing module, then passed (5 passed). Vitest `tests/monitoring-state-lane-y.test.js` 4 tests.
- Paper-only path found: none; the badge and route name no strategy kind, a real trade's row can use `MonitoringBadge` as is.
- Pending owner read: every sentence in `explanations.py` ids `monitoring_*`; fallback words in `lib/monitoringState.js`.
- Owner test (market CLOSED, Saturday): stop the worker process, wait 2 minutes, reload Live Strategies, Positions, and the builder of a running trade: each shows "⏸ Monitoring paused", "Health unknown", "Not being watched: no worker has reported in the last 2 minutes." Start the worker: within 30 s the badge goes.

### Opus review of item 1 (Why Opus: it tells a trader whether his stop is being watched): REVISE, then fixed
- Fixed: (1) a failed or old read kept the cached "active" -> now a failed read or an answer older than 90 s overrides every cached entry (test added); (5) a non-ASCII reason code made the whole reply a 500 -> ASCII-only check (test added); (7) the page joined two server sentences -> two spans; (8) builder badge no longer needs the Drafts-Mode paper book.
- Not fixed, for the coordinator: (2) nothing on this branch writes the snapshot until Lane J2's worker half is merged: every Running trade reads "Not being watched: the worker's report cannot be read" until then (fails closed). (3) J2's worker never prunes `self.status` of a dropped strategy and keeps a previous ACTIVE across `market_closed` and a user pause: check in J2's review. (4) heartbeat and snapshot are judged within +-120 s of the database clock: a wrong worker clock widens the 2-minute window. (6) `since_text` has a time but no date and resets when the worker restarts.
- Field renamed `watch_state` (the status-word source scan forbids `status === 'literal'` in page code).
- Route shape changed after the order-closure guard (`test_order_closure_all_routes`) refused a `strategy_store` import: `GET /api/monitoring-state?ids=1,2` (the ids the page shows, at most 50); it answers each asked id, never leaves one out. The page sends only trades its own server status word calls Running/open. A foreign id gets the worker's answer for that id (no user data in it).

## Item 1b (coordinator message, second in queue): ADR-330 (64), a real position's row and alert
- Tag = the stored fact, not the name: `position_kind.kind_of(has_order, has_paper_order, held_at_broker)`: held entry (ADR-292, a condor held at the broker is a REAL position stored as practice orders) -> real; order and no paper order -> real; paper order -> paper; no order -> none (draft); any fact unreadable -> unknown. Server fields `position_kind` + `position_kind_text` on every `/strategies` row and every `/alerts/active` row (`strategy_store.kinds_of`, one read).
- Sentences (catalogue, pending owner read): `position_kind_real` "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only."; `position_kind_unknown` "Cannot tell whether this is a real or a paper position, so Exit and Stops are not shown. Check it in Kite."
- Page: Live card shows Exit and Stops only when `position_kind === 'paper'` (exactly), else the line; Alerts page offers "Exit the position" only for paper (the server leaves it out of `answers` for real/unknown/none and the page re-checks; `exitFor` opens only for paper). A missing field reads unknown (fail closed).
- Tests: `tests_app/test_position_kind_adr330_64.py` (kind table, line, alert answers), `frontend/tests/position-kind-adr330-64.test.js` (real/paper/unknown/missing card), `alerts-actionable.test.js` (real/paper/unreadable alert). Existing fixtures got `position_kind: 'paper'`.
- Server refusal of an exit or stop request for a real position through the paper route: NOT built here (`routes/paper.py` is Lane K's). For lane K: in the paper exit and stop-set handlers, load `strategy_store.kinds_of(db, [id])` and refuse with the `position_kind_real` sentence unless the kind is `paper`; add a test posting an exit for a held-at-broker strategy.
- Not done: the Positions page REAL group (`PositionsPage.vue`, Lane L closed) already has no Exit/Stops link besides the PlanDoor; Home / My Strategies rows are not read for the tag: list under "Home / My Strategies, not built": show `position_kind_text` there if they offer Exit or Stops.
- Paper-only path found: Live card Exit/Stops and the Alerts Exit door lead only to paper screens (the reason for this item).
- Monday 09:45 step (market open, the one real Zerodha position): open Live Strategies: that position's card shows its P&L and "Real position: exit and protect it in Kite. Stops and alerts here cover paper trades only." and NO Exit and NO Stops links; a paper card still has both. If any alert fires on the real position, Alerts shows no "Exit the position" button. Zerodha disconnected: no real row exists, so this cannot be seen on Saturday.

## Item 2: one Plan watch request for the Positions list
- Merged origin/perf/speed-fixes-1127 (conflicts only in generated files: openapi.json, findings INDEX, reply_inventory.py: regenerated). The page-wide queue `planWatchQueue.js` was not in the base: copied as one file from hotfix/plan-watch-load-1127 (the merge conflicts in plan_watch.py, Lane H/R3's).
- `PaperStrategies.vue`: ids of open rows (sorted), chunks of 20 (`PLAN_WATCH_BATCH_MAX_ROWS`), each chunk one job through the queue (one read in flight, next batch 20 s later); re-read when the id set or the list's good-read token changes; `PlanWatch.vue` takes an optional `view` prop (null = "Reading..." until the batch answers; a given view means the box reads nothing itself; the builder's box is unchanged).
- Test (`tests/plan-watch-mounts.test.js`): 25 open rows -> exactly 1 `GET /plan-watch?strategy_ids=...` request on load (the second batch waits its queue gap), no `/strategies/{id}/plan-watch` request; a refused row (404) shows no figure and the good rows keep theirs. Claim is the request count only; no speed figure.
- PC step (market closed): Positions with at least 5 open rows: network tab filtered on `plan-watch`: ONE `/api/plan-watch?strategy_ids=...` per cycle, none of `/api/strategies/<id>/plan-watch`.

## Item 3: the not-live notice once at the top (ADR-330 (56)): NOT BUILT
CONFLICT above. Lane N's `priceScope` / `tileNotLive` / `PRICE_GREYED_CLASS` are not in this base (`frontend/src/lib/priceState.js` here lacks them), so the diff in `lane-n-for-lanes-v-l.md` ("For lane V") cannot apply alone. Next command for the coordinator, once Lane N's branch is merged into the base: `git merge origin/fix/last-close-1127`, then apply that diff to `PaperStrategies.vue` (it touches only the tile class, the reason line, the `scope`/`tile` computeds and `affected`) with the two tests the note prints.

## Item 4: side-closed question with or without a plan (ADR-330 (46)): For lane J2
Lane V had already read it: neither half is in the code. The patch `lane-m-side-closed-noplan.patch` edits `backend/ofo_app/background.py` (the worker, Lane J2's) and applies cleanly to this branch (`git apply --check` prints nothing). Exact change for lane J2: (1) `git apply docs/design/next-batch-2026-11-26/lane-m-side-closed-noplan.patch`; (2) run `tests_app/test_background_cycle.py` and `tests_app/test_side_closed_alert.py`; (3) add the missing second-half test: raise the question with a plan, REMOVE the plan, run the cycle twice, expect ONE open `side_closed` row that stays until answered, and no second row. Page side: `AlertsPage.vue` already lists whatever the server holds; nothing to change.

## Home / My Strategies, not built
Both read `status_word` only; if they offer Exit or Stops for a real position, show `position_kind_text` and hide them (item 1b). Not checked (Lane L closed).

## To file as deferred issues
1. Server refusal for an exit/stop request on a real position through the paper route (Lane K, text under item 1b).
2. J2 findings 3 and 4 of the Opus review (stale ACTIVE after a strategy is dropped; clock skew widens the 2-minute window).
3. `since_text` has no date and resets on worker restart.
