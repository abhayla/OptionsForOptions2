# Brief: GC-IC1 step 4c - REQ-155 AC-1, REQ-170: A-37 (watch a level) stored per strategy and evaluated as a rule through the alert gate

Core: a user's watched index level for a strategy (A-37) is stored per strategy (with the user who set it and the direction, above / below) and evaluated by the playbook evaluator as a yes/no rule (`watch.level` style Identifier-safe id) through `gate_readings` into the alert gate, so a crossing opens ONE adjustment record (it is an adjustment alert, not a risk exit: REQ-170 AC-5 risk exits stay outside the gate).
Proof: step 1 of this brief - the REAL background Worker with a pinned clock on a fresh DB: watch NIFTY above 23,800 on a scenario strategy; spot 23,790 -> no record; spot 23,805 at the next candle close -> one record "watched level reached"; further ticks above -> still one; spot back to 23,780 then 23,810 -> re-armed by the gate's yes/no rule, a second record.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, build-range-applied-to-recognition
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - a second alert system beside the gate (decided: through the gate, one writer, ADR-237 (6)); a rule id outside the Identifier pattern; a watch with no owner or set by another user (refused); a watch read per check from the DB on the hot path (read on the rebuild like the 4a pause); the 4a A-37 rule-object code left half-wired (remove or reuse it, one path). Out of scope - the screen inputs (step 4b), REQ-041 conditional exits (unchanged).
Sensibull: catalogue-raw.md line 222 (conditional exit on an index level) is the nearest reference; ours only alerts.
Reference: none - searched watch a level, alert only, index level
Copy from: step 4a's pause table + store + route pattern (0037, strategy_pause_store.py, routes/monitoring_pause.py); step 1's day-rule reading pattern in playbook_eval.
Tier: A (alert path).
Size: M, about 9 files, 1 item
CI: the app job runs the new tests_app files under `pytest-app.ini`; the backend unit job runs `tests/adjustment`; vars: TEST_DATABASE_URL (CI postgres; locally db_run_fresh sets it)

## Decision (orchestrator, technical; record in the report and the ADR row it adds)
A-37 is an adjustment alert, so it takes the adjustment-alert path: stored per strategy (one active watch per strategy per direction; set / clear by its owner), evaluated as a yes/no rule through the alert gate (ADR-237 (6) one writer). Add a short ADR row (next free number) stating this and amending ADR-238's list of non-trade approaches.

## Where
`git switch -c build/gcic1-s4c <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). DB tests one db_run_fresh process at a time.

## Do, in order
1. Failing worker proof first, then storage (migration 0038, additive, insert-only like 0037), store, routes (GET / PUT / DELETE, owner-only, level a positive number, direction above / below), evaluator rule, the record's words (catalogue, pinned pending owner read).
2. Remove or reuse 4a's unsaved A-37 rule-object code (one path).
3. Guard test: the new rule id matches IDENTIFIER_PATTERN.
4. Run the new DB files one at a time, `python -m pytest -q tests/adjustment`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `tests_app/test_alembic_migration_guard.py` and `tests_app/test_migration_sql_parses.py` (db_run_fresh), ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (a) the watch is read on the rebuild pass with the strategy, never a DB call per check.
- B4 (d) answer states: watch set / none / cleared / another user's / level not a number / no spot (no reading, never False).
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s4c.

Attack list:
1. A crossing opens a record outside the gate: grep; through the gate only.
2. A risk exit gated by the watch: no (REQ-170 AC-5).
3. The watch fires every tick above the level: one record per episode.
4. Another user's PUT on my strategy: 404.
5. Mutants (scratch copy, at most 5): compare with > for >=; direction ignored; watch never re-arms; read per check; colon in the id. Each turns a test red; report mutant -> test name.
