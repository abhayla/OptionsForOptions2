# Row 8 fix round 1: REQ-050 shared computation (W-136) - one snapshot instant, guards green, every affected test run

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13).
Size: M, 10 files, 6 items
CI: kit tests job (`tests/marketdata/*`, `tests/outcome/*`, `tests/errors/test_write_allowlist.py`,
`tests/test_door_names_private.py`; vars: none); app job `api` step (`tests_app/test_strategy_live_push.py`,
`tests_app/test_outcome_*.py`, `tests_app/test_chain_live.py` and every file in item 6; vars: TEST_DATABASE_URL only) -
run them through `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`
(NOT db_run.py: the worktree has no .env; the launcher uses the main checkout's).

Core: two readers of one live snapshot share every market-wide figure (each leg's IV and Greeks, each expiry's
forward): the second reader computes nothing.
Proof: step 1 is a failing test on the recorded frames (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`)
through the REAL outcome path (not a fake cache): two readers of the same snapshot one second apart on the clock -> the
second reader's new IV and forward computations are 0. At d20287f0 they are not (independent review: IV keys carry each
quote's time and the request clock's years; `_newest` makes them stale on arrival).

Spec basis: REQ-050 AC-1: "Shared once for all users: normalization, shared Greeks, underlying state, option-chain
metrics, contract metadata, market-wide derived metrics." REQ-050 AC-3: "No identical market metric is computed
separately per user." ADR-053 (V1: per user's own feed, so the feed owner stays in every key).
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head d20287f0. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row08-fix1`.

## What to do (orchestrator decisions, technical; independent Opus design review 2026-10-22: ADOPT WITH CHANGES)
1. ONE snapshot instant for the whole answer: the latest frame time among the spot and the quotes actually read,
   capped at no later than the clock. It becomes `snapshot.valuation` and is used for every figure - IV, Greeks,
   forward AND the strategy's P&L/scenario (the engine already refuses mixed instants: `model.py:180-181`,
   `service.py:364-365`). Keep the expired-contract and session-end checks on the REAL clock, so after 15:30 IST no
   contract is valued with time left. Every cache key uses that one instant; drop the per-(owner, underlying)
   `_newest` rule that evicts IV entries on arrival (`shared_compute.py:108,122,152-155`), keep a bounded size.
2. Forward key: add the expiry close and the days-per-year convention; make the quote set order-independent (sorted);
   re-run mutation M8 (forward key without the quotes) against the test the builder added
   (`test_a_changed_chain_at_the_same_instant_never_reads_the_old_forward`) and report it.
3. The two red repo guards caused by d20287f0: `tests/errors/test_write_allowlist.py` (likely the `slot.value,
   slot.done = ...` writes to a non-self object) and `tests/test_door_names_private.py` (likely the `getattr` in
   `SharedKey.__post_init__`): open each failure, fix the code (write through self/methods, no getattr), never loosen
   the guard.
4. The hanging test (mutation M4: a global lock held while computing hit the 60 s timeout): make "a slow key does not
   block other keys" FAIL fast (a bounded wait on the other key's result, e.g. 2 s), proven by re-running M4.
5. Row-2 stale test: `tests_app/test_strategy_live_push.py::test_start_with_a_session_builds_the_socket_without_logging_the_token`
   passes on main and fails on the branch: its fake socket rejects the `on_reconnect` keyword row 2 added to
   `KiteSocket`. Update the fake to accept it (the test's point - no token logged - unchanged).
6. R13: for every backend file changed in rows 8 (this branch's d20287f0 + your commits), grep the `tests_app` files that
   import it or call its routes (outcome, planned entry, chain, live push, tracking, outcome charges, checked-at...) and
   run them ALL through the launcher; list each file and its result.

Attack list: (each names its test file)
1. Two readers one second apart on one recorded snapshot -> 0 new IV and forward computations for the second
   (`tests/marketdata/test_shared_compute.py`, through the real outcome path).
2. A newer frame for one contract -> a new snapshot instant -> new entries, the old ones evicted by size, never served
   (same file).
3. The CURRENT column reprices to the LTP at the snapshot instant (no 7% gap at 1 min to close) (`tests/outcome/`).
4. At 15:30:01 IST an expiring contract is not valued with time left although its last frame is 15:29:58
   (`tests/outcome/`).
5. A changed chain at the same instant never reads the old forward; quotes in a different order share the entry
   (`tests/marketdata/test_shared_compute.py`).
6. Two users' feeds with identical data never share (same file).
7. The two repo guards and every item-6 app test file pass (commands above).

Standing items: (a) a slow computation for one key does not block another key's read (item 4, fails fast); (b) n/a:
no CI step changes; (c) the class-table import check stays an allow-list and fails closed; (d) n/a.
Threat model: in scope - a reader served another snapshot's figures, a figure valued with time left after the close, mixed instants in one answer; out of scope - a licensed shared vendor feed.
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted, wall-clock-assertion-flakes-under-load
Reviewer checklist: the real outcome path in the core test (no fake cache); one instant end to end; real-clock expiry
check; M4 and M8 re-run; guards fixed in code, not loosened; every item-6 file listed with its result; no new duplicated
literal; reuse the existing helper; ruff baseline must not rise; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
