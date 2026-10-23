# Verifier brief: builder sequence rows 12-14 (REQ-072 index spot, REQ-032 calculation engine, REQ-033 expiry and live
# P&L formulas / W-140, W-141, W-142), Tier A, start check of rows marked "verified" (one shared verifier)

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked file
in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-12-14`.

Goal contract step 3: rows whose starting state is "verified" are NOT bypassed - re-check every acceptance criterion on
today's code; old evidence is never trusted on its own (example: evidence/W-075/AC-7.md proved a basis ADR-167 later
reversed). Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`,
head f9a8d780 (rows 1-10 changed shared code since these rows were verified - e.g. row 8 made one snapshot instant per
answer and shared Greeks, row 9 moved the feed - so earlier evidence may be stale). Specs: `spec/requirements/REQ-072.md`,
`REQ-032.md`, `REQ-033.md` (every AC), the decisions each cites, and `spec/business-rules/scenario-calculations.md`
(the locked formulas). Earlier work items and evidence: W-059, W-060, W-114 (REQ-072); W-002, W-039, W-074 (REQ-032);
W-001, W-063, W-082 (REQ-033) - grep `evidence/` for them; use them as leads, not proof. For the engine use the project
skill checklist `options-math-review` (read `.claude/skills/options-math-review/SKILL.md` with the Read tool).

Attack first: (1) an independent hand computation for at least 3 real cases from the recorded frames
(`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`): a NIFTY iron condor's expiry P&L at 3 levels, its live
P&L now, one leg's IV and delta - compare with the engine to the paisa (Decimal); (2) money is Decimal end to end
(`float(` only inside `engine/black_scholes.py`); (3) row 8's one-instant valuation and shared Greeks give the SAME
numbers as an unshared read; (4) the index spot (REQ-072) is the gated live spot, never a stale or other-index value,
and its health label follows REQ-049; (5) expiry day after 15:30 IST values no time left; (6) delete each engine guard in
a scratch copy and name the killing test (`python scripts/orchestrator/mutation_gate.py` when its fix round has landed,
else a script writing each result to `verify-12-14\mutation-results.jsonl` as it finishes - R18).

You run AHEAD of row 10 (ADR-171: rows 12-14 checked while row 10 is verified; they close only after rows 10 and 11).
The OLDER row has the database first: run NO database test in this dispatch - run the engine, scenario, table and
outcome tests (no database needed) and list every DB-backed test file these ACs depend on as "DB part queued"; the
orchestrator runs that part when row 10's database work is done. Database (for that later part only): ONE run at a time (ADR-171): every DB test through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
- it now holds a lock and WAITS while another row's run holds it (an older row goes first); start it first in the
background (R16); never bypass the runner. Most engine tests need no database (tests/engine, tests/scenario,
tests/table, tests/outcome): run those directly. Known failing, not these rows:
`tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`.
Do NOT call Kite live.

Why Opus: Tier A (the one engine owns every P&L number; a wrong formula is a wrong figure on every screen).

Return a JSON array, one object per row per AC: `{"row": 12, "req": "REQ-072", "ac": "AC-n", "result": "pass" |
"fail" | "partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 300 words:
each fail/partial with severity and the smallest fix, the hand computations (inputs, your figure, the engine's), and
anything not checked. Stop every process you start before you report.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
