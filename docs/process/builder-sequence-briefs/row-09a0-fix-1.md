# Row 9 part A0 fix round 1: REQ-113 feed process core (W-137) - pin the five unguarded guards

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13-R16).
Size: M, 4 files, 6 items
CI: app job `api` step (`tests_app/test_bus_socket.py`, `tests_app/test_feed_restart_core.py`,
`tests_app/test_feed_process_boundary.py`; vars: TEST_DATABASE_URL, OFO_REQUIRE_DB_TESTS=1, REDIS_URL from the
`redis:7` service) - locally with REDIS_URL at the pure-Python stand-in (F-58) as the existing fixtures do.
Expected (orchestrator, before dispatch 21:40 IST): fix 30 min / ~120k; verify round 2 20 min / ~170k. Tests only: the
verifier found no code defect.

Core: an old price is never shown as live across the bus: a frame is judged by the time the FEED received it.
Proof: step 1 is the new late-frame test failing on mutation M04 (the API stamps frames with its own clock) and passing
on the code - the round-1 verifier already proved exactly that with a scratch version: set the API clock to T0+10 s,
publish a frame the feed received at T0, assert the quote reads STALE.

Spec basis: REQ-113 AC-3: "After a bus loss, every consumer marks its data stale (ADR-015) until a fresh tick or a fresh
Zerodha read arrives." REQ-113 AC-2: "Restarting or redeploying the API process does not close any user's Kite socket".
REQ-113 AC-7: "every Kite call it makes goes through the egress gate (REQ-073 AC-4, ADR-098), like the API process."
Copy from: none beyond the map rows below.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 117f38dc. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row09a0-fix1`.
The verifier's mutation script and mutant list (reuse them; do not rewrite):
`...\scratchpad\verify-09a0-mt\mutate.py`, `mutants.jsonl` (M04, M07, M11, M13, M19 survived; the other 17 were killed).

## What to do (verify round 1 findings; tests only - change product code ONLY if a new test proves a defect)
1. MAJOR (M04): in `tests_app/test_bus_socket.py`, a late-frame test where the API clock is T0+10 s (beyond the stale
   window) and the frame's feed receive time is T0 -> the quote is STALE, never live. Re-run M04 -> red.
2. M07: the API's `want` key expires when the API stops refreshing it -> the feed drops those tokens (test, M07 red).
3. M19: a dead feed's status key lapses -> the API reads the feed as not connected (test, M19 red).
4. M11: a status key written for another user is never read as this user's status (test, M11 red).
5. M13: a subprocess test of `feed_main._main` with no session: the egress gate is installed BEFORE it exits with code 3
   (`feed_main.py:101`, `prepare_process()`); M13 red. Use the existing test-only launcher pattern and plain
   `subprocess.Popen` (no asyncio subprocesses on Windows).
6. Route the core test's API through `LiveMarket.start` with `FEED_MODE=bus` (`tests_app/feed_launcher.py:45-51` calls
   `LiveMarket.attach` directly today), so mutation M15 (bus swap removed) is killed by the core test too.
Then run all 22 mutants with the verifier's script: 22 of 22 red; list each with its killing test.

Attack list: (each names its test file)
1. A frame the feed received at T0 read when the API clock is T0+10 s -> STALE (`tests_app/test_bus_socket.py`).
2. The API stops refreshing `want` -> the feed unsubscribes within the expiry (`tests_app/test_bus_socket.py`).
3. The feed dies -> its status lapses -> not connected, never "live" (`tests_app/test_bus_socket.py`).
4. User B's status key is never read as user A's (`tests_app/test_bus_socket.py`).
5. `feed_main` without a session: gate installed first, exit code 3, no Kite call (`tests_app/test_feed_process_boundary.py`).
6. API restart through `LiveMarket.start` in `bus` mode: feed `connections` stays 1, fresh frames reach the new API
   (`tests_app/test_feed_restart_core.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (the redis service exists, app-tests.yml:153-161); (c) n/a: no static detector; (d) Redis answer states already listed in test_bus_socket.py - the new expiry cases (want lapsed, status lapsed) are added to that list.
Threat model: in scope - an old frame shown live, a lapsed feed read as connected, another user's status read as this user's, a Kite call before the egress gate; out of scope - a hostile local process writing to Redis.
Findings checked: wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later
Reviewer checklist: each new test red on its mutant and green on the code; 22 of 22 mutants red; no product-code change
unless a test proved a defect; clock-driven tests use the fake clock, never sleep; R16 timing reported; no new
duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated
files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 60 tool calls
Report: evidence-table
