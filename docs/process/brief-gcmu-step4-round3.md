# Brief: GC-MU step 4 fix round 2 (last) - one failure never stops the background role for every strategy

Core: an exception anywhere in a cycle (list re-read, one strategy's type/playbook lookup, the instrument list, the speed read) is logged and contained; the loop keeps running and every other strategy is still checked on the next cycle.
Proof: step 1 of this brief - failing tests first on the real `Background.cycle` / `run` / `owner_lister`: the list reader raises once -> the next cycle still checks the strategies from the last good list; one strategy's `resolve` raises -> the other strategies are listed and checked; the speed reader raises -> the cycle uses the last good speed (none yet: the cycle is skipped and logged) and `run()` keeps looping.
Budget: 35 min wall-clock, 45 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 3/3 (fix round 2 of 2; what is not green after this is PARKED)
Class: unguarded exception paths in a long-running loop. Tier A read-only review of 98b54260 (MAJOR, REQ-115 AC-9): `backend/ofo_app/background.py` `cycle()` calls `rebuild()` and `background_seconds()` outside the per-strategy `try`; `run()` has no `try`; `owner_lister` catches only `TrackedExited` / `TrackedUnreadable` per strategy, so one strategy's `strategy_type` / `resolve` / `instrument_master()` error, a database error in the 30 s re-read, or a refused speed setting ends the process for every strategy, and nothing restarts it. Population: every exception raised outside `_check_one`; before: each one stops all checks; after: each one is logged, counted in `self.errors`, and contained to its strategy or its cycle. Also MINOR (AC-4): `_check_one` sets ACTIVE before `background_state`; an exception there leaves the strategy ACTIVE though it was not checked - on that exception set PAUSED (reason "check failed") so a later screen reading the status never shows an unchecked strategy as active.
Proof (class): the failing-first tests above, plus a mutant per guard (remove each new `try`) turning its test red, run by you on the worktree with the original text restored.
Spec quote: REQ-165 AC-2 "A strategy is checked when a price it depends on changes"
Findings checked: staleness-by-last-change-age, dependent-tests-not-run-stale-later
Threat model: in scope - one strategy's or one read's failure stopping every check (REQ-115 AC-9); a strategy shown active though unchecked (AC-4). Out of scope - a process supervisor / restart service and the heartbeat alert (REQ-115 AC-6, NOT DONE, parked with the Notifier part), the feed's wanted key (step 4b, merged).
Sensibull: n/a - server background role, no screen.
Reference: none - searched background checks (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - fixes this repo's own new module.
Tier: A (the orchestrator re-runs the mutants; the reviewer's MAJOR is the checklist).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-bg`, branch `build/gcmu-bg`, on top of 98b54260. Change only `backend/ofo_app/background.py` and `tests_app/test_background_cycle.py` (and `test_background_worker.py` only if a DB-side test is truly needed). Same read-only files as before. Commit there only, never push.

## Do, in order
1. Failing tests first (non-DB, in `tests_app/test_background_cycle.py`, injected clock, no real sleeps): (a) lister raises on the 2nd rebuild -> the cycle keeps the last good `monitors` and still checks them; (b) `owner_lister` with one strategy whose `check.resolve` (or `strategy_type`) raises -> the other strategy is still listed (inject the failing call; do not edit adjustment_check.py); (c) `read_speeds` raises -> no crash, last good speed kept (or the cycle skipped when there is none), logged; (d) `run()` with a cycle that raises once -> the loop runs the next cycle; (e) `_check_one` raising after ACTIVE -> status PAUSED. See each one red, then fix.
2. Fix: per-strategy `try` in `owner_lister` (log + skip that strategy, never the list); `rebuild()` failure keeps the previous list; speed read failure keeps the last good value; `run()` catches and logs a cycle's exception and continues (never swallow `asyncio.CancelledError` / `KeyboardInterrupt`: catch `Exception` only); `_check_one` sets PAUSED on its own exception (in `cycle`'s except, by strategy id).
3. Mutants on the worktree (restore the exact original text after each, never with git from a script): remove each new `try` in turn -> its test red. Report each.
4. Run: `tests_app/test_background_cycle.py`, `tests_app/test_background_worker.py` (via `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-bg python -m pytest -c pytest-app.ini tests_app/test_background_worker.py -q -rs`), guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, `python scripts/ruff_ratchet.py`. Logs to a file, tail only.

## Standing items
- `except Exception` only, each with `log.exception` naming the strategy or the step; never a bare `except:`.
- No new duplicated literal; ruff baselines must not rise.
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-bg.
