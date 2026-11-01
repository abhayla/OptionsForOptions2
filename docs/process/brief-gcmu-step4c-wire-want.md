# Brief: GC-MU step 4c - the background worker writes its strategies' leg tokens to the feed (4b key)

Core: each cycle, the worker writes the instrument tokens of every monitored strategy's legs (plus each underlying's index token) with `feed_bus.write_background_want(client, owner, tokens)`, so with no screen open the feed still subscribes them.
Proof: step 1 of this brief - a non-DB test with a fake Redis: a worker monitoring ADJ-02's strategy runs one cycle with no API snapshot; `feed_bus` relay `refresh_want` on the same fake Redis then wants exactly those tokens.
Budget: 25 min wall-clock, 35 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Sensibull: n/a - server feed plumbing, no screen.
Reference: none - searched wanted tokens (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - wires two modules built in this run (steps 4 and 4b).
Tier: B (the orchestrator reviews the diff).

## Where
New worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-wire`, branch `build/gcmu-wire` (from `build/gcmu` 02a00755, which has both `background.py` and `feed_bus.write_background_want`). Change `backend/ofo_app/background.py` and tests only. Do not edit `feed_bus.py`, `adjustment_check.py`, `playbook_store.py`, `live_market.py`, `paper_monitor.py`. Commit there only, never push.

## Do, in order
1. CORE: in the worker, after each successful `rebuild()` and at least once per `feed_bus.WANT_REFRESH_S` (the snapshot has an expiry, `WANT_TTL_MS`), write ONE snapshot per feed owner: the tokens of all its monitored strategies' legs plus their underlyings' index tokens (find how the API side maps a tradingsymbol to its instrument token - grep `instrument_token` / the instrument master the provider already exposes; reuse it, no second lookup table). Test as in Proof.
2. Answer states, one test each: no monitored strategies (write an EMPTY snapshot so stale wishes lapse, or write nothing and let the TTL lapse - pick one, say which and why); a leg whose token cannot be found (that strategy shows PAUSED with the existing "no price for one leg" reason, the others still written); Redis not answering (logged, counted in `errors`, the cycle continues - the step 4 fix round made this the rule); a token list above `feed_bus.MAX_WANTED_TOKENS` (refused by feed_bus; log it, never cut silently).
3. Run: `tests_app/test_background_cycle.py`, `tests_app/test_feed_background_want.py`, the new test file, `tests_app/test_background_worker.py` via `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-wire python -m pytest -c pytest-app.ini tests_app/test_background_worker.py -q -rs`, guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `python scripts/ruff_ratchet.py`. Logs to a file, tail only.

## Standing items
- The write is inside the cycle's existing failure containment (one failure never stops the role).
- No new duplicated literal; ruff baselines must not rise. Tests that import `ofo_app` under `tests_app/`.
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-wire.
