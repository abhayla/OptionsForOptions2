# Brief: GC-MU A5 - the Compare's "Adjustments used" row fed from the GC-ADJ2 adjustment history count

Core: `Tracked.adjustments_used` is filled from the engine's adjustment history (`backend/ofo/engine/adjust_history.py` `adjustment_history(...).adjustments_used`) instead of None, so the Compare row shows a number.
Proof: step 1 of this brief - on scenario ADJ-13 (one adjustment already made) the Compare's "Adjustments used" cell reads the history count (1 for "No change", 2 for an approach that trades), not "-".
Budget: 25 min wall-clock, 30 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Spec quote: REQ-156 AC-2 "adjustments used against the plan's maximum"
Sensibull: n/a - the reference product has no adjustment counter (searched the study for adjustments used).
Reference: none - searched adjustments used, adjustment history (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - GC-ADJ2 built the history.
Tier: C (small reader change; tests + self-check are the gate).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-used`, branch `build/gcmu-used` (from `build/gcmu`). Commit there only, never push. Today `backend/ofo_app/adjustment_readers.py` (~line 109-112) returns `adjustments_used=None` with the comment "the paper book records no adjustment history yet". GC-ADJ2 has since built `adjustment_history` (engine) - find its app-side reader (grep `adjustment_history(` under backend/ofo_app) and reuse it; never count closed-and-reopened legs (that was called a guess and stays forbidden).

## Do, in order
1. CORE: fill `adjustments_used` from the history reader; one answer per state, each tested: history read gives N (the number); history cannot be read (None -> the existing "-" with its reason, never 0); no adjustment yet (0).
2. Scenario mode: ADJ-13 must show the count through the route (the route test file `tests_app/test_adjustment_approaches_route.py`, run through `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-used python -m pytest -c pytest-app.ini tests_app/test_adjustment_approaches_route.py -q -rs` - the worktree has no .env).
3. Run in full: the route file as above, `tests/engine/test_adjust_history.py`, `tests/adjustment`, `python scripts/ruff_ratchet.py`, guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`. A shown-value change: grep `frontend/tests` and `frontend/e2e` for the old "-" expectation of this row and update any that pin it.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-used.
