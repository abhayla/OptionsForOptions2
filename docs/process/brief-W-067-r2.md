# Builder brief: W-067 round 2 - never block the feed; finalize at real-day size (Tier A review, 2026-10-10)

Core: (a) a recorder write returns to the feed thread in milliseconds whatever the database does (slow, locked, down);
(b) finalize of a full trading day (about 1,603 instruments x 375 minutes, F-33) completes within a bounded time.
Proof (step 1, red first against 7ba7f49): a tests_app test holding `pg_advisory_xact_lock(6700067)` (or `LOCK TABLE
history_minute_bars IN ACCESS EXCLUSIVE MODE`) from the owner session while the recorder writes asserts the caller
returns in < 100 ms - today it blocks 15.06 s (review probe); and a finalize scale test (marked so CI runs the full size)
asserting a set-based finalize of 1,603 x 375 synthetic-but-valid bars finishes under a stated bound - today 240
instruments did not finish in 480 s.

Tier: A. Model: sonnet/medium. Budget: 60 min wall-clock, 75 tool calls. Commit after each numbered step; at budget
stop after a commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none.

## RCA and Class
- RCA (a): `PostgresHistoryStore` waits on `.result()` on the feed thread (`history_store.py:101`) with only the 15 s
  command timeout as a bound; `FanOut.pump()` calls subscribers on one thread, so every subscriber waits.
- RCA (b): `_slice` (`history_store.py:256`) looks bars up by a named-key list that plans as a full scan + nested loop
  (6.8 s for 240 keys over 90k rows; 21.5M rows filtered); finalize then writes per minute in one transaction.
- Class (a): every recorder write (bars, gaps) on every feed thread; (b): every finalize run, sized by instruments x
  minutes. Before: 15 s blocks; no completion at 240 instruments. After: < 100 ms caller time under a locked DB, bars
  queued (bounded, counted when dropped, the drop filled later by the existing gap/backfill path); finalize set-based.
- Detection: the two tests above, plus the CI-sized run.

## Spec basis
- REQ-051 AC-5: "Historical data and simulation never block live strategy creation, Option Chain, execution or monitoring"
- REQ-051 AC-4: "Aggregated history is built from the live feed where practical and licensed (Q169)"

## What to fix
1. **Non-blocking writes:** the recorder hands writes to a bounded queue drained by one background writer (thread or
   task) that owns the database calls; the feed path never waits on the database. Queue full -> the bar is dropped,
   counted, and recorded as a gap so finalize backfills it from Kite (ADR-067). Writer errors never reach the feed.
   Keep the one-writer-per-rule contract (the store contract tests still pass against the PG store).
2. **Set-based finalize:** index for the lookup the store does (e.g. (trading_day, instrument_id, minute)); load
   candles into a temporary table (COPY or executemany) and apply them with set-based UPDATE/INSERT in batches (per
   instrument chunk), each batch its own transaction, resumable (a re-run continues; a final day is never rewritten).
   Run ANALYZE where the job creates bulk rows. State the measured time per batch.
3. **Completeness, not a time margin:** finalize refuses (and leaves the day provisional, retryable) unless Kite's
   candles cover the session's last minute for every instrument that has live bars that day; keep the 15:40 IST
   earliest start (F-33). Test: candles missing the last minute -> refused, day still provisional.
4. **MINORs from the review:** advance `_gaps_sent` (`recorder.py:66`) only after `record_gaps` succeeds; database
   CHECKs matching the store: a removed bar only by the finalize path's rules (or document why not), no INSERT of an
   already-removed row, prices with at most 2 decimal places refused, not rounded (NUMERIC without scale + a CHECK, or
   an equivalent); owner TRUNCATE stays as in 0001-0008 (note it).
5. **Scale test placement:** the full-size test runs in CI's own PostgreSQL (app-tests job); locally run it at a SMALL
   size only (e.g. 40 instruments) - this PC's PostgreSQL also serves IPODhan production (owner decision 2026-10-09).
   Mark it so CI runs the full size (e.g. an env var the CI job sets) and say how.

## Reviewer checklist (each must turn a test red)
- Writer back on the feed thread; queue unbounded; a writer error reaches the feed; finalize per-row again (the CI
  bound fails); finalize with a missing last-minute candle succeeds; `_gaps_sent` advanced before success.

## Rules
- Targeted tests only, from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-067 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_pg_store.py tests_app/test_history_finalize_job.py <new files>`;
  migration changes: 0009 is not on main, edit it in place, then via the same runner `python -m alembic -c
  backend/ofo_app/alembic.ini downgrade 0008_strategy_store` and `upgrade head`; leave the DB at your 0009 head.
  Domain: `python -m pytest -q -p no:cacheprovider tests/history`. Grep tests/ and tests_app/ for every function and
  table you change and run each file that names one. CI mirror:
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-067 W-067 --no-tests`.
  If you change `.github/workflows/app-tests.yml` (project-owned, not kit) to pass the scale env var, read it with the
  Read tool and edit with Edit (the kit guard blocks shell text naming .github).
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files or
  `spec/`. Never write `evidence/`. Never mark anything verified. Push `build/W-067-history-pg`.
