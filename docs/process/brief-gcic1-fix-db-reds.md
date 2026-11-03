# Brief: GC-IC1 fix - REQ-165 / REQ-155: DB-test reds on feature/adjustments after steps 1, 3 and 6a (rule ids outside the Identifier pattern; route tests assuming every approach has a whole-trade figure)

Core: every rule id the evaluator produces (day rules, situation rules) matches the API's Identifier pattern (ADR-069, `ofo.strategy.settings_value.IDENTIFIER_PATTERN` = `[A-Za-z0-9_.-]{1,64}`), so the screen check never answers 500 when a day or situation rule is in its results; and the approaches-route DB tests hold for approaches that deliberately have no whole-trade figure (A-04 spans two expiries).
Proof: step 1 of this brief - on a fresh DB (feature/adjustments head given in the dispatch, measured 2026-11-03 15:06): `tests_app/test_adjustment_check.py` 6 failed (500: "String should match pattern ... input_value='sit:S-02'"), `tests_app/test_adjustment_approaches_route.py` 11 failed (ConversionSyntax on `D(g["max_profit"])`, NoneType not subscriptable, A-36 drawer list), `tests_app/test_adjustment_plan.py` 1 failed (500, same cause): after the fix all three files pass on a fresh DB.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-155 AC-1 "the server builds the exact legs from the listed strikes, reusing the REQ-078 server strike moves, and prices them"
Threat model: in scope - loosening the shared Identifier pattern (do NOT: it guards every id in the API); a test "fixed" by deleting its assertion (each skip must name the approach and why it has no figure); stored rule ids of the old form (only test and dev databases hold any; the restore path must not crash on an old id - test it). Out of scope - new behaviour.
Sensibull: n/a - ids and tests.
Reference: none - searched rule id pattern, identifier
Copy from: none.
Tier: B (ids + tests; the DB files are the gate).
Size: S, about 5 files, 2 items
CI: the app job runs the three tests_app files under `pytest-app.ini`; the backend unit job runs `tests/adjustment`; vars: TEST_DATABASE_URL (CI postgres; locally db_run_fresh sets it)

## Where
`git switch -c build/gcic1-db-reds <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). You hold the ONLY DB slot: `python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`, one process at a time.

## Do, in order
1. Rule ids: day rules `day.<when>.<HHMM>.<action>` (e.g. `day.expiry.1430.5`), situation rules `sit.S-02` / `sit.S-12`; one id-builder function per kind; update every reader of the old form (grep `day:` and `sit:` in backend and tests, including the generator and the gate's group keys). A pure guard test: every rule id `playbook_eval.evaluate` can produce for the iron condor body (and the 37824fb9 body) fully matches IDENTIFIER_PATTERN.
2. Approaches-route tests: an approach whose After has no whole-trade figure (A-04, by design: two expiries) is compared on what it has (trades, cost) and named in the test as figure-less; the A-36 drawer test's generic list updated to the current approaches (list the change).
2b. `tests_app/test_t19_cheapest_cost.py` (10 failed at 15:1x: KeyError 'A-24', cheapest-cost maps predating A-02..A-38): its expectations follow the generator (ADR-221: cheapest offered approach, now including the step 2/3 approaches); derive expected values from the generator's `hand_cheapest`, never retype numbers; list every expectation that moved and why (e.g. ADJ-02's cheapest is no longer A-29 at Rs 92.35 if a new approach is cheaper).
3. Run the four DB files (one at a time), `python -m pytest -q tests/adjustment tests/test_adjust_scenarios.py`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states: new id form / old id in a stored row (read without crash, never re-opened as a new rule - test).
- ruff / mypy baselines must not rise; regenerated scenario files only if ids appear in them.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-db-reds.

Attack list:
1. A colon left anywhere in a produced rule id: the guard test catches it.
2. IDENTIFIER_PATTERN loosened: grep; unchanged.
3. A-04 assertion simply deleted: the test still checks A-04's trades and cost.
4. Old stored id `day:expiry:14:30:5` crashes the restore: test it does not.
5. Mutant: put a colon back in the situation id -> the guard test turns red.
