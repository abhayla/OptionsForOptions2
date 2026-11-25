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

## Phase 2..8: not started
