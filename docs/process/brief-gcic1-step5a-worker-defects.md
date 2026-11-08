# Brief: GC-IC1 step 5a - REQ-165 / REQ-170 / ADR-235: diagnose and fix #638 (3 xfail worker tests) and #639 (3 follow-ups)

Core: the three worker behaviours #638 marks xfail (each style checked at its own interval; a plan change uses the new ladder; the IST day rollover resets the daily cap) work on the REAL background Worker, so their xfail(strict=True) markers come off.
Proof: step 1 of this brief - each of the three tests in tests_app/test_background_worker.py run one at a time with -k on a fresh DB: first diagnosed (the test's timing or the worker: name which, with the line), then passing with the marker removed.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: check-clock-read-once-per-batch, staleness-by-last-change-age, engine-input-chosen-per-caller
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Threat model: in scope - a weekly strategy checked after 60 s instead of 30 s (slower alerts); a plan change ignored until restart; a cap that never resets after midnight IST, or resets on a UTC day; the screen and the worker disagreeing on a quiet index's spot (#639 item 1); a dismiss matched by rule instead of by record (#639 item 2); the old style's interval used once after a style change (#639 item 3). Out of scope - #627 (T-13 / T-16, step 5b), #636 (latency, step 5c), day rules (step 1).
Sensibull: n/a - background worker timing, no screen.
Reference: none - searched check interval, day rollover, dismiss by record
Copy from: none (worker internals of this repo); reuse the existing helpers named in #639.
Tier: A (worker; fresh Opus review follows; mutation tests required).
Size: M, about 6 files, 6 items
CI: the app job runs `tests_app/` under `pytest-app.ini` (worker tests); the backend unit job runs `tests/` for any pure helper; vars: TEST_DATABASE_URL (CI postgres service; locally db_run_fresh sets it)

## Where
`git switch -c build/gcic1-s5a <sha given in the dispatch>` inside your agent worktree (feature/adjustments, never main, never push). DB tests ONLY through
`python D:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_background_worker.py -k <name>`
The whole file takes ~14 min: always -k one test; run the whole file once, LAST. Long output to a log file, tail only.

## Read first (do not re-survey)
- GitHub #638 and #639 (`gh issue view 638`, `gh issue view 639`): every symptom, file and line is there.
- `backend/ofo_app/background.py` (per-style interval ~line 822, dismiss ~278-280, feed_spot), `backend/ofo_app/adjustment_readers.py:290`, `backend/ofo/marketdata/spot_source.py:98-113`, `backend/ofo/adjustment/alert_gate.py` (daily cap, `restore`), `backend/ofo/adjustment/alert_presets.py`.
- Findings check-clock-read-once-per-batch (each check reads its own clock) and staleness-by-last-change-age (freshness by connection, never by last-change age).

## Do, in order
1. CORE: diagnose each #638 test one at a time (-k). For each: is the defect in the worker or in the test's own timing? Name the line. Fix the cause (worker or test, never a looser assertion that hides a worker defect); remove the xfail marker; the test passes.
2. #639 item 1: one freshness function for the screen and the worker (connection-aware, the worker's rule), the screen calls it; a test gives both callers the same quiet-index input and asserts the same answer.
3. #639 item 2: dismiss matched by record id, not by rule; a test opens a record during the rebuild read window and asserts it is not marked dismissed.
4. #639 item 3: after a style change the next check uses the NEW interval; test monthly -> intraday waits at most the intraday interval.
5. Close #638 and #639 only through the merge commit body (`Fixes #638`, `Fixes #639`) when every item is done; otherwise name what is left.
6. Run the whole tests_app/test_background_worker.py once (fresh DB), the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, ruff on changed files, `python scripts/ruff_ratchet.py`, mypy on changed backend files (compare with the base commit).

Standing items:
- B4 (a) no new loop with its own time budget; the per-cycle cap stays.
- B4 (d) answer states for the spot read: fresh / stale / feed disconnected / no tick yet today / market closed; each tested for both callers.
- Each check reads its own `now`; tests use an injected clock, never real sleeps.
- ruff / mypy baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s5a.

Attack list:
1. The interval test passes only because its own sleep is longer (looser timing): the fix must not widen the expected gap set beyond {30}.
2. Day rollover computed in UTC (05:30 IST is midnight UTC): test 23:59 -> 00:01 IST resets; 05:29 -> 05:31 IST does not.
3. Plan change read only at restart: test the new ladder applies on the next rebuild without a restart.
4. Screen and worker freshness: same input, same answer, for a quiet index 10 s after its last tick with the feed connected.
5. Mutants (scratch copy only, at most 5): rollover by UTC date; style interval cached at start; dismiss by rule id; screen keeps the 3 s last-change window; per-style interval ignored (one global). Each turns a test red; report mutant -> test name.
