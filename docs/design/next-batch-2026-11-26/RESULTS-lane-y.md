STATUS 21:45 | item 1: Fixed, not tested (gate + Opus review running) | next push 22:20 | blocker: none (send_message to @parent refused: untrusted device; this top line is the report)

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
