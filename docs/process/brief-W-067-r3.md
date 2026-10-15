# Builder brief: W-067 round 3 - finalize exactly as ADR-067 says; domain tests never import the app

Core: a trading day becomes final when the after-close fetch succeeds; a minute Kite has no candle for keeps its live
bar (ADR-067) - no day-level completeness refusal; and no domain test under `tests/` imports `ofo_app`.
Proof (step 1, red first against 90b39cb): the review's three in-memory reproductions (a thin strike whose live bar is
one minute after Kite's last candle; an instrument recorded live but missing from the retry's instrument list; an empty
Kite answer for an instrument with live bars) each end `provisional` today and must end `final` with the live bar kept
for the uncovered minutes; and `python -m pytest tests/history tests/execution/test_safety_checks.py` in ONE process
fails today (1 failed) and must pass.

Tier: A. Model: sonnet/medium. Budget: 30 min wall-clock, 45 tool calls. Commit after each numbered step; at budget
stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none.

## RCA and Class (the orchestrator's round-2 brief caused defect 1)
- RCA 1: the round-2 brief ordered "finalize refuses unless Kite's candles cover the session's last minute for every
  instrument", written without re-reading ADR-067, which says the opposite for a minute without a candle. Any one
  uncovered instrument then holds the whole day provisional forever, with no exit.
- RCA 2: `tests/history/test_finalize_completeness.py` imports `ofo_app.history_finalize`; importing `ofo_app`
  installs the W-024 root log redaction, which strips `exc_info` from later tests' records in the same process
  (`tests/execution/test_safety_checks.py:640` failed in CI run 38021452764 and locally).
- Class 1: every finalize run for every instrument set. Class 2: every module under `tests/` (the kit CI's domain
  suite, standard library + ofo only).
- Detection: the three reproductions as tests; a guard test that parses every `tests/**/*.py` with `ast` and fails on
  an `import ofo_app` / `from ofo_app ...` statement (string mentions of the name, as in the producer inventory and the
  secret-scan tests, are not imports and stay allowed).

## Spec basis
- ADR-067 decision: "a minute Kite has no candle for keeps the live bar"
- ADR-067 consequence: "A day that could not be made final (no session, Kite error) stays provisional and is named as such"

## Do
1. Finalize (`backend/ofo/history/finalize.py`, `backend/ofo_app/history_finalize.py`): remove the completeness refusal
   and the incomplete status path; a successful fetch makes the day final; uncovered minutes keep the live bar; a fetch
   error or no session keeps the day provisional and named (ADR-067 consequence). Earliest start 16:00 IST (orchestrator
   decision: a 20-minute margin after the latest observed trading, SENSEX expiry 15:39, F-33, so the last candle exists).
2. Move every test that needs `ofo_app` out of `tests/` into `tests_app/` (pure-domain parts stay in `tests/history`).
3. The `ast` guard test (e.g. `tests/test_no_app_imports.py`, beside the other repo-wide guard tests) with a self-test
   that a temporary file containing `from ofo_app import x` is caught.
4. Make the full-size scale test's timings visible in the CI log (e.g. put the measured total and slowest batch in the
   assertion message AND emit them via `record_property` or a printed line that pytest shows with `-rA`/`-s` - choose
   one that appears in `gh run view --log`).
5. The coverage register: add `W-067: 4a` under `work_items` in `docs/process/coverage-stages.yaml` and regenerate with
   `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\coverage.py C:\Abhay\Ventures\OptionsForOptions2-W-067 --write`.

## Reviewer checklist (each must turn a test red)
- Re-add any day-level refusal for an uncovered instrument; drop the live bar of an uncovered minute; `import ofo_app`
  in any `tests/` file; finalize before 16:00 IST.

## Rules (this PC also serves IPODhan production's database)
- Grep `tests/` and `tests_app/` for every function, status and constant you change and run each file that names one.
  From the worktree: `python -m pytest -q -p no:cacheprovider tests/history tests/execution/test_safety_checks.py`
  (one process, the CI order case) and `python -m pytest -q -p no:cacheprovider tests/test_no_app_imports.py`; from
  `C:\Abhay\Ventures\OptionsForOptions2`: `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-067 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_nonblocking.py tests_app/test_history_pg_store.py tests_app/test_history_finalize_job.py <moved files>`
  (small sizes only - the full-size test runs in CI). CI mirror:
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-067 W-067 --no-tests`.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files or
  `spec/`. Never write `evidence/`. Never mark anything verified. Push `build/W-067-history-pg`.
