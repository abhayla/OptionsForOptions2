# Brief: GC-IC1 step 5c - #636 round 5, REQ-165 / ADR-220 (3): the background check makes no DB call on its path (round 4 design + the round-4 FIX FIRST findings)

Core: the background worker's check path reads settings from an in-memory cache and writes records through one per-strategy writer queue, so a steady-state check makes ZERO DB statements, while the four round-4 FIX FIRST findings hold: only the settings row IN FORCE per key is validated; queued writes for a strategy removed or re-planned at rebuild are dropped; the writer task is watched (a dead writer is restarted and logged) and drained on stop; LAG_SECONDS counts the wait for the shared lock.
Proof: step 1 of this brief - on build/gcalert1-636r4 merged with the feature/adjustments head: the existing proofs re-run green (0 DB statements over 150 checks in steady state; settings_cache, cycle, speeds, calc files on a fresh DB), then failing tests first for each finding: (1) an insert-only replaced row of 45 with a release max of 30 and the in-force row 20 -> reload succeeds and checks continue after a restart; (2) a strategy exits while its write is queued -> no record opens; (3) the writer raises once -> it is restarted, the queued write lands, a log line names it; stop() -> the queue drains; (4) a rebuild holding the lock for 2 s -> LAG_SECONDS includes it.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 5 (parked twice; the contract re-opens it: "#636 round 5 (merge base first, guard tests, record merge commit in #636; the round-4 FIX FIRST findings)")
Findings checked: check-latency-bound-by-db-round-trips, check-clock-read-once-per-batch, staleness-by-last-change-age
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - a settings cache that validates every historic row (finding 1: one bad replaced row stops all checks); a write for a strategy that just exited (finding 2: an alert nobody can lapse); a writer that dies silently (finding 3); a lag figure that hides lock waits (finding 4); a second connection outside the pool budget (role limit 5, `config.py:42-45`); `shown_at` touched (not insertable by the app role, `0031:123`). Out of scope - the live 1.0 s measurement (D3, needs market hours: step 9 of GC-IC1); LISTEN / NOTIFY (dropped by the 2026-11-02 review).
Sensibull: n/a - server-side worker.
Reference: none - searched settings cache, writer queue, check latency
Copy from: build/gcalert1-636r4 5bf1db31 (round 4 code: settings cache + count poll + writer queue) - build on it, never restart from scratch.
Tier: A (worker, every alert).
Size: M, about 8 files, 4 items
CI: the app job runs `tests_app/test_background_settings_cache.py`, `test_background_cycle.py`, the speed/calc files under `pytest-app.ini`; vars: TEST_DATABASE_URL (CI postgres; locally db_run_fresh sets it)

## Where
In your agent worktree: `git switch -c build/gcic1-636r5 5bf1db31`, then `git merge <feature/adjustments sha given in the dispatch>` (B1: merge the base first), resolve conflicts keeping the head's behaviour plus round 4's design, run the guard tests and the round-4 proof files BEFORE any new change, and write the merge commit sha in a comment on #636 (`gh issue comment 636`). DB tests one db_run_fresh process at a time; if another is running, wait.

## Do, in order
1. Merge + guard + round-4 proofs (record the merge sha on #636).
2. The four findings, failing tests first.
3. SPEC CHANGE note if the cache can lag: REQ-166 AC-1 / REQ-167 AC-4 wording of the next check would become a bounded delay of N seconds, N named (round-4 design point 6): write it in the report, NOT in the spec (the orchestrator decides and writes the spec).
4. Run the touched DB files one at a time, `python -m pytest -q tests/adjustment`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.
5. Do NOT close #636 (the live D3 measurement is still owed).

Standing items:
- B4 (a) zero DB statements per check in steady state stays asserted.
- B4 (d) answer states: settings row in force valid / invalid (the key falls back to its registry default, named) / replaced rows invalid (ignored); writer alive / died / stopping.
- Fail closed: rule memory set only after a successful write (round 4 held this; keep it).
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-636r5.

Attack list:
1. A replaced bad row stops reloads: test (finding 1).
2. A record for an exited strategy: test (finding 2).
3. Writer death unnoticed: test (finding 3).
4. A second DB connection opened by the poll: at most one at a time (test).
5. Mutants (scratch copy, at most 5): validate every row; never drop stale queued writes; no writer watchdog; lag without the lock wait; memory set before the write. Each turns a test red; report mutant -> test name.
