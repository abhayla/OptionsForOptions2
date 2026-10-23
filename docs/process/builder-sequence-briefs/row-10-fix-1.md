# Row 10 fix round 1: REQ-118 (W-138) - CI reds from row 10 and row 9, one untested guard, one stray bucket

Common brief: docs/process/builder-brief.md (Budget hard stop: at 48 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` for u8b and every guard you add; quote its results file (R18).
Size: M, 7 files, 5 items
CI: kit tests job (`tests/execution/test_margin_gate.py`; vars: none); app job `api` step
(`tests_app/test_kite_login.py`, `tests_app/test_zerodha_rules_cited.py`, `tests_app/test_broker_token_store.py`,
`tests_app/test_rate_limit_door.py`, and the R13 list `...\scratchpad\row10\dbfiles.txt`; vars: TEST_DATABASE_URL only).
Expected (orchestrator, before dispatch, clock 10:4x): 40 min / ~150k. This is row 10's fix round 1 (verify round 1
PARTIAL); a failed round 2 PARKS row 10.

Core: CI is green for row 10's code: no test fails because of rows 9-10, and no test's 429 cooldown leaks into the next.
Proof: step 1 - the three red groups reproduce first (the verifier's commands): `tests/execution/test_margin_gate.py::test_ac3_zerodhas_figure_alone_decides`,
`tests_app/test_kite_login.py` (6 failed at f9a8d780, passed at 83707b70), `tests_app/test_zerodha_rules_cited.py`
(`MARGIN_BUSY_CODE ... not in the registry`), and `tests_app/test_broker_token_store.py` (10 failed "expected 5, got 4":
fail at 83707b70 and f9a8d780, pass on main 3ccc8439 - row 9 part B's one-read change); then all green.

Spec basis: REQ-118 AC-1: "the limiter applies them at the scope Zerodha states (per app key or per user)" (F-60: the
stricter reading - one bucket per group for the whole app). REQ-118 AC-4 ("retried after the wait Kite indicates, at
most twice"). REQ-113 AC-8 and row 9 part B (the one-read session expiry, `access_session_for`).
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head f9a8d780 - the only
agent writing here. Leave the orchestrator's uncommitted files alone. Commit ONLY your own paths with
`git commit -F <msg> -- <your paths>`; never `git add -A`, `stash`, `checkout --`, `reset`, `restore`; do NOT push.
BINDING: never stop a process by name; stop only PIDs you recorded. Database only through `fresh_launch.py` (the one
lock). Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row10-fix1`; the verifier's notes and mutants:
`...\scratchpad\verify-10\`.

## What to do
1. `test_margin_gate.py::test_ac3_zerodhas_figure_alone_decides`: the gate's signature gained `busy`; update the test to
   assert `busy` is keyword-only and words-only (the test's point - Zerodha's figure alone decides - unchanged).
2. Test isolation: an autouse fixture (tests_app conftest) installs a FRESH limiter per test (the process-wide limiter
   kept a real 10 s cooldown from one test's 429 case); the 6 `test_kite_login.py` failures pass; production keeps one
   limiter per process.
3. `MARGIN_BUSY_CODE`: list it in the registry's `NOT_A_ZERODHA_RULE` (it is our refusal code, not a Zerodha rule).
4. Row 9's token-store tests (10 failures "expected 5, got 4"): find what row 9 part B's one-read `access_session_for`
   changed (the query now returns 5 columns? the fake row 4?) and fix the TESTS or the code to the one-read design -
   the design stays (the verifier of row 9 proved it); name the cause in the report.
5. u8b (the async re-check after a cooldown, `rate_limit.py:200`) gets a killing test; the instrument download (no
   Authorization header) shares the app's "other" bucket, not a separate `-` bucket (F-60: one bucket per group for the
   whole app).
Out of scope (orchestrator: deferred issues): the real Notifier sender (AC-6 - an egress change, its own reviewed item);
renaming `rate_limit.py` to a Kite module; the `429` literal retyped in both door modules.

Attack list: (each names its test file)
1. The margin-gate test green with `busy` keyword-only (`tests/execution/test_margin_gate.py`).
2. A 429 case in one test never changes the next test's result (`tests_app/test_kite_login.py`).
3. The rules registry test green (`tests_app/test_zerodha_rules_cited.py`).
4. The 10 token-store tests green, cause named (`tests_app/test_broker_token_store.py`).
5. u8b red without the re-check (`tests_app/test_rate_limit_door.py`); a request with no Authorization header uses the app's "other" bucket (`tests/broker/test_rate_limit.py`).
6. The full R13 list green except failures that also fail on main (classified with the main run) (report).

Standing items: (a) background jobs never take a user action's slot ahead of it (keep green); (b) n/a: no CI step changes; (c) the door-coverage scan keeps failing closed; (d) Kite's answer states for a limited call stay listed in `tests_app/test_rate_limit_door.py`.
Threat model: in scope - CI red at the chunk PR, a test result depending on another test's state, a stray bucket doubling the app's call rate; out of scope - the real Notifier sender.
Findings checked: dependent-tests-not-run-stale-later, wall-clock-assertion-flakes-under-load, process-kill-by-name-hits-others
Reviewer checklist: every red group green with the cause named; isolation by fixture, not by sleeping; one bucket per
group; R13 list classified; gate results quoted; no new duplicated literal; reuse the existing helper; ruff/mypy
baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
