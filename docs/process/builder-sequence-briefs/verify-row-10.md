# Verifier brief: builder sequence row 10 (REQ-118 Zerodha rate limits for read calls / W-138), Tier A, round 1

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a tracked
file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-10`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head f9a8d780
(row 10 = 83707b70..f9a8d780, the builder's commits only; 83842bf3 is a separate process item - ignore it). Spec:
`spec/requirements/REQ-118.md` (every AC), F-60 and F-57 in `spec/findings.md`, ADR-017, ADR-094. Builder brief:
`docs/process/builder-sequence-briefs/row-10-REQ-118-rate-limits.md` - run every item of its `Attack list:` again.

In scope: AC-1, AC-2, AC-3, AC-4, AC-6; AC-5 on the one write that exists (`POST /session/token` is never retried);
trigger writes are not built - report that part `deferred`.

Attack first: (1) find EVERY Kite REST call path (grep the door modules, `urllib`, `httpx`, `open_url`, `KiteReads`,
`KiteMargin`, `kite_history`, `downloader`, `kite_client`) and prove each passes the ONE limiter - a call that skips it
is a CRITICAL; (2) both door modules share one bucket per group (a urllib quote and an httpx quote in the same second);
(3) the limits come from one registry with source URL and date (F-60) - none typed elsewhere (grep 1/s, 3/s, 10/s,
"10.0", "3.0"); (4) a 429 -> nothing is sent to that group for 10 s (the window must not be extended by our own
retries), a read retries at most twice, then busy, and the margin gate then BLOCKS (ADR-094) - never a wrong margin
figure; (5) a user action never waits > 5 s; the queue is bounded; a background burst never starves a user read; (6)
`POST /session/token` is never retried on 429 or timeout; (7) three 429s in a minute raise exactly one alert, the
fourth none; no token in any log or alert body; with no NOTIFIER_URL nothing breaks; (8) the busy text has one home;
(9) delete each guard in scratch copies and name the killing test - use `python scripts/orchestrator/mutation_gate.py`
(commit 83842bf3) with your own mutants file, results to `verify-10\mutation-results.jsonl`.

Database: ONE run at a time (ADR-171): run the R13 selection for row 10's own backend diff through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`,
started FIRST in the background (R16); never start a second DB run. Known failing, not this build:
`tests/test_edit_lint_hook.py::test_real_eslint_run_flags_unused_variable`,
`tests_app/test_broker_status_route.py::test_core_proof_a_stored_session_reads_connected_and_ending_it_reads_disconnected`.
A live Kite session exists on the live API (:8765); do NOT call Kite live - every check here uses fakes.

Why Opus: Tier A (every Kite call, the margin gate's input, and a burst that could get the platform's key blocked).

Return a JSON array, one object per AC: `{"row": 10, "req": "REQ-118", "ac": "AC-n", "result": "pass" | "fail" |
"partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked. Stop every
process you start before you report.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
