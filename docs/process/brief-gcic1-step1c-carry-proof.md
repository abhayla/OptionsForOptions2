# Brief: GC-IC1 step 1c - REQ-159 AC-4: the carry-check record's gap figures checked against independent generator values

Core: the worker's carry-check record on ADJ-53 carries 2% gap figures that match values the generator computes on its own (its own leg model, not the app's code path), within one tick per leg.
Proof: step 1 of this brief - the generator writes `expected.carry.gap_up` / `gap_down` for ADJ-53 and ADJ-55; tests_app/test_day_rules_worker.py asserts |record - expected| <= 0.05 x quantity x legs (Rs 26 for ADJ-53: 0.05 x 130 x 4); ADJ-55 (before-holiday, Monday 9 Nov) runs through the worker and opens one record.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: engine-input-chosen-per-caller
Spec quote: REQ-159 AC-4 "Each carries a time and one action: carry check, show reduce or exit, show add-hedge, pause, tighten every"
Threat model: in scope - the expected value computed through the app's own carry function (then it proves nothing); a tolerance wide enough to pass a valuation at expiry or with up and down swapped. Out of scope - new behaviour.
Sensibull: n/a - test data only.
Reference: none - searched carry check, gap figures
Copy from: none.
Tier: B (tests and generator only).
Size: S, about 3 files, 1 item
CI: the app job runs `tests_app/test_day_rules_worker.py`; the backend unit job runs `tests/test_adjust_scenarios.py`; vars: TEST_DATABASE_URL (CI postgres service; locally db_run_fresh sets it)

## Where
Continue on branch `build/gcic1-s1b` in the worktree `D:\Abhay\Ventures\OptionsForOptions2\.claude\worktrees\agent-a496dbf65328faf86` (head 8c044eea). Commit there only, never push.

## Why a tolerance, not the paisa (orchestrator's technical call, recorded)
The worker solves each leg's IV back from prices rounded to the 0.05 tick and the forward from the chain; the generator prices from the exact IV. An exact match would need the generator to reuse the app's pricing path, which would make it no longer independent. One tick per leg per unit of quantity bounds the rounding; the wrong-valuation mistakes the test must catch move the figures by thousands of rupees (ADJ-53: -8430.50 up vs -1007.50 down).

## Do, in order
1. Generator (`tests/adjust_scenarios_gen.py`, never importing the app's carry code): for a carry case, whole-trade P&L (booked plus open legs) at spot x 1.02 and x 0.98 at the next session's 09:15 IST, each leg at its own generator IV (`iv_at`), with the generator's own rate and option formula as it already prices its chain; Fraction or exact Decimal; written to `expected.carry`. Regenerate only ADJ-53..55 (diff the other files: unchanged).
2. Worker test: assert the tolerance above for ADJ-53; add ADJ-55 through the worker (1 record after the 15:01 close).
3. Show the tolerance catches the mistakes: on a scratch copy, value at expiry instead of the next open, and swap up/down: both turn the test red; report each.
4. Run tests_app/test_day_rules_worker.py through `python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_day_rules_worker.py`, `tests/test_adjust_scenarios.py`, ruff on changed files, `python scripts/ruff_ratchet.py`. The guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan` only if a non-test file changed.

Standing items:
- B4 (d) n/a beyond the cases above (test data only).
- Exact arithmetic; no float. No regenerated aggregates beyond the three case files and INDEX.md if it lists them.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s1b.

Attack list:
1. The expected value imports the app's carry function: grep the generator; it must not.
2. Tolerance too wide: valuing at expiry passes: must be red.
3. Up and down swapped passes: must be red.
4. Valued at today's time instead of the next open (one weekend of decay missing): state the size of the difference on ADJ-53 and whether the tolerance catches it.
5. ADJ-55 opens two records (before-holiday AND before-weekend) on a Monday: must be exactly one (Monday is not before a weekend).
