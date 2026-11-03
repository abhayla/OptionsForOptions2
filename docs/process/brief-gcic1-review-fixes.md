# Brief: GC-IC1 Tier A review fixes (areas A and B, 2026-11-03) - REQ-159 AC-4, REQ-165 AC-5, ADR-241

Core: the four accepted review findings are fixed at class level: (A1) a day rule with a malformed time can never produce a rule id outside the Identifier pattern (refused when the playbook is saved, fail-closed id if one is ever read); (A2) the worker reads the strategy's margin whenever a rule that uses it is on (T-16 OR a carry day rule), so a worker carry record carries the same margin as the screen; (B1) the approach planned price uses the ONE mid function (`ofo.marketdata.forward.mid_price`, half-even) like `iv_price`; (B-open) the approach cost's half-spread (`compare.py` `approach_cost`) uses a book only when it is live (ADR-172 health gate), else names the cost not known.
Proof: step 1 of this brief - failing tests first: (A1) saving a playbook whose day rule has `at` of 2:30 pm (not HH:MM) is refused with a named reason, and `day_rule_id` on such a stored body never returns an id outside IDENTIFIER_PATTERN; (A2) worker vs screen on a Friday 15:00 carry scenario with T-16 switched OFF: both records carry the stated margin; (B1) bid 100.00 / ask 100.05 live -> 100.02 (today 100.03); (B-open) a stale book after hours -> the half-spread cost is not taken from it.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, build-range-applied-to-recognition
Spec quote: REQ-159 AC-4 "Each carries a time and one action: carry check, show reduce or exit, show add-hedge, pause, tighten every"
Threat model: in scope - a second mid formula left anywhere (grep `/ 2` near bid/ask in backend/ofo/adjustment and backend/ofo_app); the margin read moved onto the per-check hot path (it stays the 5b per-strategy cache, only its "which strategies" condition widens); a playbook save refusing bodies that were valid before (only a malformed `at` is refused). Out of scope - the generator's symmetric bid/ask (known limit, unit tests cover mid vs LTP).
Sensibull: n/a - server-side fixes.
Reference: none - searched day rule time, margin cache, bid ask mid
Copy from: none.
Tier: A (alert and money paths; the orchestrator re-runs the proof tests).
Size: M, about 6 files, 4 items
CI: the backend unit job runs `tests/adjustment`, `tests/engine`; the app job runs the touched tests_app files under `pytest-app.ini`; vars: TEST_DATABASE_URL for the playbook-save and worker tests (CI postgres; locally db_run_fresh sets it)

## Review evidence (accepted)
- Area A finding 1: `backend/ofo/adjustment/playbook_eval.py:701-702` `day_rule_id` builds from `at` unchecked; `at: "2:30 pm"` -> `day.expiry.230 pm.5`; `playbook_store.py:306-311` only checks `day_rules` is a list; the check route types `rule_id` as Identifier (`routes/adjustment_check.py:73`).
- Area A finding 2: the worker fills its margin cache only for strategies with T-16 on (`background.py:397-400`, used at `:985`); carry figures read `state.margin` (`adjustment_check.py:310`).
- Area B finding 1: `backend/ofo/adjustment/approaches.py:246` own mid with half-up; the one mid is `backend/ofo/marketdata/forward.py:120` `mid_price` (half-even, used by `iv_price`).
- Area B open point: `compare.py:242` `approach_cost` reads bid / ask without the health gate.

## Where
`git switch -c build/gcic1-review-fixes <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). DB tests one db_run_fresh process at a time; another builder (step 4c) may also need the DB: if a db_run_fresh is already running (check the process list for db_run_fresh), wait for it.

## Do, in order
1. Failing tests (the proof), then the four fixes.
2. Run `python -m pytest -q tests/adjustment tests/engine tests/test_adjust_scenarios.py`, the touched tests_app files (DB ones one at a time), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states: `at` valid / malformed / missing; margin stated / busy / failed / no rule needs it; book live / stale / crossed / one side missing.
- Exact Decimal (ADR-008); one mid function.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-review-fixes.

Attack list:
1. A second mid formula remains: grep shows one.
2. A malformed `at` still reaches the check route: the save refuses it and the id builder fails closed.
3. Margin read every cycle after widening the condition: the 5b ten-cycles test still passes.
4. A stale book's half-spread used after hours: refused.
5. Mutants (scratch copy, at most 5): half-up back in planned_price; carry rule not counted for the margin; `at` unchecked; health gate dropped in approach_cost; id builder not fail-closed. Each turns a test red; report mutant -> test name.
