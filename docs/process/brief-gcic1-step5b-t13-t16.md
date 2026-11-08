# Brief: GC-IC1 step 5b - #627 items 1 and 2, REQ-165 AC-5: T-13 (gap at the open) and T-16 (loss vs margin) answered by the screen AND the background worker

Core: the check's StrategyState gets `day_open` from the feed's own day values of the index (`QuoteBook.latest_day_stats`, REQ-080 AC-7) on both the screen and the worker, and the worker gets the strategy's broker margin through the screen's margin reader (rate-limited, cached per strategy), so T-13 and T-16 answer the same on both paths for the same scenario.
Proof: step 1 of this brief - on a scenario case pinned at 09:20 IST with a 1.2% gap at the open (a new generator case if none exists), the pure evaluation fed by the worker's state and by the screen's state both answer T-13 fired with the same value; T-16 with a stated margin answers the same on both paths; with the margin read failing both answer not_checked missing_margin.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, check-clock-read-once-per-batch, staleness-by-last-change-age
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - a second day-open reader beside the quote book's; the worker calling the broker margin API every cycle (rate limit: Kite allows about 1 REST call per second per key, shared with every screen); a stale margin used without its age; a day_open from the previous session (the packet's day fields after a restart before the first tick of the day). Out of scope - #627 items 3-6 (restart service, heartbeat alert, screen reading the worker's result, valuation time), #636 latency (step 5c).
Sensibull: n/a - server-side rule inputs.
Reference: none - searched day open, gap at the open, margin in background; RD-032, RD-132 and RD-133 (REQ-080 open difference records, screen display of depth and day values) untouched: this step only reads the day values on the server
Copy from: none; reuse inside this repo, listed below.
Tier: A (worker; fresh review follows only if the proof fails).
Size: M, about 7 files, 2 items
CI: the backend unit job runs `tests/adjustment`; the app job runs `tests_app/test_background_cycle.py` / `tests_app/test_adjustment_readers.py` (pure, fakes) under `pytest-app.ini`; vars: none unless a DB test is added (then the orchestrator runs it, one DB job at a time)

## Where
`git switch -c build/gcic1-s5b <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). DB tests ONLY when the orchestrator says no other DB job runs; prefer pure tests with fakes.

## Reuse (grep before any new function; report each as reused / new-with-reason)
- Day values: `backend/ofo/marketdata/feed_health.py` `QuoteBook.latest_day_stats(instrument_id, now)` -> `DayStatsAnswer` (stats or reason: NOT_HELD / FEED_NOT_HEALTHY / PACKET_WITHOUT_DAY_FIELDS); `DayStats.day_open` (`backend/ofo/marketdata/provider.py`). The index must be held when read (finding live-subscription-lost-on-release-reacquire: read INSIDE the hold; the round-3 fix of the screen check adds a shared hold-and-read helper - use it if merged at your base, else read where the index is already held).
- T-13 rule: `backend/ofo/adjustment/playbook_eval.py` `_t13` (reads `state.day_open`, `state.prev_close`, `gap_until`); fill `day_open` in `backend/ofo_app/adjustment_check.py` `state_of` (one place both paths use; today the docstring says "day_open: no reader").
- Margin: the screen's reader (`get_approach_margin` / `backend/ofo_app/kite_margin.py`, `KiteBusy` from `ofo.broker.rate_limit`); the worker passes margin None today (`background.py` ~36, ~322). Give the worker a cached per-strategy margin with its read time, refreshed at most once per N minutes per strategy (N from the settings store if a key exists, else a named constant with a MERGE-SWAP comment) and only for strategies whose playbook has T-16 on; a failed or busy read -> margin not known (missing_margin), never the last value without its age.

## Do, in order
1. CORE (failing tests first): the parity proof above (screen state vs worker state, same answers for T-13 and T-16).
2. day_open: stale-day guard - a DayStats whose `last_trade_ts` is not today IST is not used (reason named).
3. Worker margin cache with the rate rule; a test that 10 cycles in a minute make at most one margin call per strategy.
4. Close #627 items 1 and 2 only (comment on #627 naming what is left: items 3-6); no `Fixes #627`.
5. Run `python -m pytest -q tests/adjustment`, the touched tests_app pure files, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (a) the margin refresh never runs inside the per-cycle check path's time budget; it is a cached read.
- B4 (d) answer states: day stats stated today / previous session / not held / feed not healthy / packet without day fields; margin stated / busy (rate limit) / failed / not refreshed yet / stale beyond its window.
- Each check reads its own `now`.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s5b.

Attack list:
1. Yesterday's day_open used at 09:16 before today's first tick: refused (stale-day guard).
2. Margin API called every cycle: at most once per window per strategy.
3. Margin busy (KiteBusy) treated as zero margin: must be not known.
4. Screen and worker disagree on T-13 for the same inputs: parity test.
5. Mutants (scratch copy, at most 5): drop the stale-day guard; margin cache never expires; margin read every cycle; worker margin None again; day_open from the leg instead of the index. Each turns a test red; report mutant -> test name.
