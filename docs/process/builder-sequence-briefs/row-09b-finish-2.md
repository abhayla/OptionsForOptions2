# Row 9 part B finish 2: REQ-113 (W-137) - killing tests for the three unproven part-B guards (tests only)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 24 calls start nothing new, commit, report).
Size: S, 3 files, 3 items
CI: app job `api` step (`tests_app/test_feed_user_isolation.py`, `tests_app/test_feed_process_boundary.py`; vars:
TEST_DATABASE_URL, OFO_REQUIRE_DB_TESTS=1, BROKER_TOKEN_KEY, REDIS_URL) - locally REDIS_URL at the stand-in (F-58).
Expected (orchestrator, before dispatch 08:25 IST): 20 min / ~90k.

Core: one user's socket failing during the feed's reconcile never touches another user's socket (AC-9).
Proof: the new isolation test is red on mutant M5a and green on the code.

Spec basis: REQ-113 AC-9: "One user's socket failure does not affect another user's socket". REQ-113 AC-3: "the bus
holds no state that cannot be rebuilt".
Copy from: none - tests only.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head d9332fe3. Commit ONLY
your own paths with `git commit -F <msg> -- <your paths>` as its own call; never `git add -A`, `stash`, `checkout --`,
`reset`, `restore`; do NOT push. Scratch: `...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09b-finish2`.
The previous finisher's mutation script and results: `...\scratchpad\row09b-finish\` (`mut-results.jsonl`, the
mutant definitions M5a, M6, M7) - reuse them; write each result to a file as it finishes.

## What to do (tests only; change product code ONLY if a new test proves a defect)
1. M5a (per-user isolation removed in the reconcile step) survived: a test where user A's socket START or STOP raises
   during reconcile while user B's socket runs -> B keeps running and its ticks keep flowing; red on M5a.
2. M7 (a feed with no stored session exits instead of idling) survived: a test that starts `feed_main` with no session,
   asserts the process is still running after the re-check interval (fake clock or a short configured interval, never a
   long sleep), and starts a socket once a session is stored; red on M7.
3. M6 (Redis down at feed start crashes) HUNG for 420 s instead of failing: bound the test (every wait bounded, e.g.
   `asyncio.wait_for` / a process wait with a timeout) so a crash or hang FAILS within 60 s; red on M6.
Re-run M5a, M6, M7 against your tests: each red within 120 s; record each in a results file.

Attack list: (each names its test file)
1. A raising start for user A during reconcile leaves B's socket and ticks untouched (`tests_app/test_feed_user_isolation.py`).
2. A raising stop for user A during reconcile leaves B untouched (`tests_app/test_feed_user_isolation.py`).
3. No session at start: the feed stays up and later starts on a stored session (`tests_app/test_feed_process_boundary.py`).
4. Redis refused at start: the feed stays up and recovers when Redis answers; a crash fails within 60 s (`tests_app/test_feed_process_boundary.py`).
5. The existing tests in both files still pass (`tests_app/test_feed_user_isolation.py`, `tests_app/test_feed_process_boundary.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) n/a: tests only - the answer states are listed in the part B tests.
Threat model: in scope - one user's failure stopping another's feed, a feed that dies before any login, a hung test hiding a crash; out of scope - none.
Findings checked: wall-clock-assertion-flakes-under-load
Reviewer checklist: each test red on its mutant within 120 s; bounded waits; no long sleeps; no product-code change
unless a test proved a defect; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise;
targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 30 tool calls
Report: evidence-table
