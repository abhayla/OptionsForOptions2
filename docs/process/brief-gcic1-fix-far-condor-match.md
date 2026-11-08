# Brief: GC-IC1 fix - REQ-076 AC-8 / ADR-186 (4): a far out-of-the-money iron condor is not recognised (no playbook, no checks)

Core: the shape matcher names a position by its shape only; the templates' build ranges (param min / max in strike steps) no longer refuse a match, so a condor whose short sits more than 20 strike steps from the money is still an iron condor.
Proof: step 1 of this brief - the owner's real position (paper strategy 82 on ofo_dev: NIFTY 29 Dec 2026, +21000 PE / -21500 PE / -24000 CE / +24500 CE, 65 each, spot about 23,674, strike gap 50) is matched as `iron_condor` by `ofo.strategy.matching.match` and typed `ic` by `ofo.adjustment.strategy_type.type_of`; before the fix the same call returns Custom with reason "param 'p'=43 outside its bounds [-20, 20]".
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: ADR-186 "does not require equal wings: a put pair plus a call pair whose wings differ is still named Iron Condor"
Threat model: in scope - build-time ranges applied to recognition; the builder or the leg picker losing its range limits (they must still refuse building past the range); positivity and order constraints (a long put above its short put is NOT a condor) dropped by mistake. Out of scope - new templates, the adjustment playbooks.
Sensibull: n/a - server-side recognition; no screen change (the builder names the shape as before).
Reference: none - searched shape matching, template bounds, iron condor recognition; RD-097 and RD-141 (REQ-076 open difference records) untouched: this fix changes only which positions are recognised, not any screen
Copy from: none.
Tier: B (ordinary app code, CI + tests; the merge is checked by the orchestrator re-running the proof).
Size: S, about 3 files, 1 item
CI: the backend unit job runs `tests/strategy/` and `tests/adjustment/`; no DB; vars: none

## Defect-fix contract
- RCA: `Template.violations(values, matching=True)` (`backend/ofo/strategy/model.py:268`) applies each `Param.violation` min / max range, which exists to limit what the builder makes, so the matcher refuses any position whose strikes are further than the range from the money.
- Class: every template param with a min / max range, every caller of `ofo.strategy.matching.match` (`ofo/adjustment/strategy_type.py` playbook typing, `ofo/reconciliation/grouping.py` imported broker positions, `ofo_app/routes/leg_edit.py` shape naming): any position whose shape fits a template but whose strike distance in steps is outside the range. Before: iron condor short beyond 20 steps (1,000 NIFTY points at gap 50) -> generic. After: recognised.
- Failing test first: the owner's four legs above through `match` and `type_of` -> red before, green after.
- Fix at class level: in matching mode, skip only the min / max RANGE check of a param; keep the int check, `must_be_positive`, and every order / sign constraint (they define the shape). Building (matching=False) unchanged.
- Proof: the test above, plus the orchestrator re-runs `/api/strategies/82/adjustment-check` on the live app after merge.
- Detection: a test that, for EVERY template, matches a position built at its default params and then moved 3x its max range away still matches the same template (so a future range cannot hide a shape again).

## Where
`git switch -c build/gcic1-far-ic <sha given in the dispatch>` inside your agent worktree (feature/adjustments; never main, never push). No DB tests needed.

## Do, in order
1. Failing tests: owner's legs (expiry 2026-12-29, lot 65, spot 23674, gap 50) -> `match` is MatchResult iron_condor, `type_of` == "ic"; and the per-template detection test.
2. The fix in `Template.violations` / `Param.violation` (matching mode only).
3. Check `tests/strategy/test_param_templates.py:62` (a covered_call "outside its bounds" case): read what it asserts (building or matching) and keep its intent; if it asserted matching refuses a far strike, that assertion is the defect, change it and say why.
4. Run `python -m pytest -q tests/strategy tests/adjustment tests/reconciliation` (log to a file, tail), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (c) the matcher stays fail-closed on shapes it cannot resolve (returns Custom, never a guess).
- B4 (d) answer states: inside range / outside range / negative where must_be_positive / order constraint broken; each tested in matching mode and in building mode.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-far-ic.

Attack list:
1. Building past the range is now allowed (matching=False path changed): test the builder still refuses p=43.
2. A long put ABOVE its short put matches as a condor (order constraint dropped): test Custom.
3. Iron butterfly vs condor ambiguity for far strikes: shorts at different strikes stay a condor.
4. Imported positions (`grouping.py`) group the owner's legs as one iron condor: one test.
5. Mutants (scratch copy, at most 5): skip must_be_positive too; skip ranges in building mode; skip order constraints; keep ranges in matching; drop the int check. Each turns a test red; report mutant -> test name.
