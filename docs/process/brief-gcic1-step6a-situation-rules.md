# Brief: GC-IC1 step 6a - REQ-159 AC-5, ADR-240 (3): situations S-02 (trending day) and S-12 (big win early) act as rules through the alert gate

Core: S-02 and S-12 of the iron condor playbook become rules the evaluator reports as yes/no readings through `gate_readings` into the alert gate (like the step 1 day rules), so each opens one record per episode offering its approaches.
Proof: step 1 of this brief - pure tests on two generator cases: (a) S-02: an iron condor whose net delta per lot is beyond +/-0.15 (engine Greeks) -> the evaluator reports S-02 True and a gate step opens one record offering the playbook's roll approaches; at +/-0.14 -> False, no record; (b) S-12: on the session the strategy was entered, profit at 40% of max profit -> True, record offering A-24 and A-25; the next session at 45% -> no reading (day 1 only); same day at 39% -> False.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller, build-range-applied-to-recognition
Spec quote: REQ-159 AC-5 "Situations S-01 to S-12 (catalogue Part 4) are part of the playbook"
Threat model: in scope - a rule that needs a NEW key in the playbook body (saved and migrated bodies would lack it: the step 1a A-27 defect class): thresholds 0.15 and 40% come from ADR-240 (3) as named constants in code until the editor exposes them, never from a new body key; a rule bypassing the gate; net delta computed outside the engine (ADR-008); S-12 judged on a date other than the entry session (IST); no reading when inputs are missing (Greeks absent, entry date unknown) - None, never False. Out of scope - the editor screen and the Guidance label (step 6b with 4b), S-03 / S-04 / S-05 (guidance, ADR-240 (1)).
Sensibull: n/a - server-side rules.
Reference: none - searched trending day, big win early, net delta per lot
Copy from: step 1's day-rule path in `backend/ofo/adjustment/playbook_eval.py` (`day_answers`, `_add_day_rules`, content-based rule ids) - extend that pattern; no parallel evaluator.
Tier: A (alert path; fresh review at the next review gap).
Size: M, about 8 files, 2 items
CI: the backend unit job runs `tests/adjustment`, `tests/test_adjust_scenarios.py`; the app job runs the touched pure `tests_app` files; vars: none (no DB)

## Where
`git switch -c build/gcic1-s6a <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). NO DB tests (another builder holds the single DB slot).

## Decision it builds to
`spec/decisions/ADR-240.md` (3): S-02 = net delta per lot (engine Greeks summed over the legs, divided by the lots of the largest leg) at or beyond +/-0.15 opens one record offering the playbook's roll approaches; S-12 = on the session the strategy was entered, profit at or above 40% of max profit opens one record offering A-24 and A-25.

## Reuse (grep before any new function; report each as reused / new-with-reason)
- Day-rule pattern and ids (step 1), `gate_readings.readings`, the record's approaches field (`'A-28,A-27'` shape).
- Net delta: the leg Greeks the state already carries (`MarketInputs.leg_greeks`, round 3's held read), summed by an engine function (`ofo/engine`; grep for an existing position-delta sum, e.g. the paper book's Greeks total) - never a new sum in playbook_eval.
- Profit and max profit: the state's `pnl` and `max_profit` (already in StrategyState); the entry session: the tracked strategy's first fill / entry time (grep `Tracked` for an entry timestamp; if none exists, add it to the tracked reader from the existing paper / position store, and name what you used).

## Do, in order
1. Failing tests first (the proof above), then the evaluator rules (ids content-based, e.g. `sit:S-02`, `sit:S-12`), then the generator cases and expectations.
2. The record names the approaches; the S-12 record's A-24 / A-25 are still subject to ADR-238 (6) (refused when not in profit - consistent: S-12 only fires in profit).
3. New user-visible text in the catalogue, pinned pending owner read; ADR-003 wording.
4. Run `python -m pytest -q tests/adjustment tests/test_adjust_scenarios.py tests/engine`, touched pure tests_app files, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) answer states: Greeks for every leg / one leg missing (no reading, reason) / entry time known / unknown (no reading) / max profit unlimited or unknown (no reading).
- Money and Greeks exact Decimal (ADR-008); engine owns sums.
- ruff / mypy baselines must not rise; no regenerated aggregates except the scenario files you add.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s6a.

Attack list:
1. S-02 thresholds read from a new body key: a pre-change saved body must still fire S-02 (test with the 37824fb9 body).
2. S-12 fires on day 2: refused.
3. Net delta per lot divides by the number of legs instead of the lots: test with 2 lots.
4. A missing Greek reads as delta 0 (then S-02 false): must be no reading.
5. Mutants (scratch copy, at most 5): threshold 0.15 as > not >=; day-1 check removed; sum outside the engine; gate bypassed; 40% of max loss instead of max profit. Each turns a test red; report mutant -> test name.
