# Builder brief: W-067 - one-minute history in PostgreSQL + the after-close finalize job

Core: bars built by the W-062 recorder from the real 2026-10-08 frames are written to PostgreSQL as ofo_app, read
back through a NEW engine exactly (Decimal paise, OI, source), and after the finalize job runs on the real Kite candles
fixture every compared minute equals Kite's candle with source "kite" - the same as the in-memory store gives.
Proof (step 1, red first): `tests_app/test_history_pg_store.py` runs the W-062 store contract against the PostgreSQL
store (red: the store does not exist) plus the replay-through-recorder comparison with the in-memory store.

Tier: A (new migration, a job that rewrites stored rows). Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Commit after each numbered step; at budget stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - legacy-reuse row 70 (`app/models/eod_option_snapshot.py`, ADAPT in P5) is the daily snapshot tier's
Decimal shape; read it for column naming only.

## Spec basis
- REQ-051 AC-3: "Tiers: real-time, aggregated intraday (1-minute/5-minute), daily, strategy snapshots (active user strategies"
- REQ-051 AC-4: "Aggregated history is built from the live feed where practical and licensed (Q169)"
- REQ-051 AC-5: "Historical data and simulation never block live strategy creation, Option Chain, execution or monitoring"

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-067`, branch `build/W-067-history-pg` from main 6fc9b6b. The
  orchestrator placed `work/W-067.md` and this brief: commit both first.
- Read `backend/ofo/history/` (store.py HistoryStore Protocol and InMemoryHistoryStore, recorder.py, finalize.py,
  candles.py, bars.py), `tests/history/test_store_contract.py` (STORES) and the other W-062 tests,
  `backend/ofo_app/alembic/versions/0008_strategy_store.py` (the latest migration: allowlist chain helper, grants, guard
  triggers with md5 pins, downgrade) and `0005`/`0007` for the pattern, `backend/ofo_app/db.py`, ADR-067 and ADR-048.

## What to build
1. **Migration `0009_minute_history`** (down_revision `0008_strategy_store`), through the existing allowlist chain:
   one table for one-minute bars keyed by (instrument identity as the catalogue holds it, minute start in IST/UTC as
   W-062 defines), OHLC as NUMERIC(14,2) (never float), volume and OI as BIGINT, source CHECK in the W-062 closed set
   (provisional / backfilled / kite), a day-status table if the store protocol has one; ofo_app grants: SELECT,
   INSERT, UPDATE only of the columns finalize changes, no DELETE/TRUNCATE; a guard so a FINAL day's rows are never
   changed again (trigger, md5-pinned like 0008); downgrade drops cleanly; a real-DB test of downgrade-then-upgrade.
2. **`PostgresHistoryStore`** (`backend/ofo_app/history_store.py`) implementing the HistoryStore Protocol exactly as the
   in-memory store does (one writer per rule - finding store-rule-enforced-per-call-site: the rules live in the domain
   store contract, the PG store does not re-implement them differently). Add it to the contract run (tests_app runs
   the contract against it; tests/ stays stdlib).
3. **Finalize job** (`backend/ofo_app/history_finalize.py`): a function (and a `python -m` entry) that, for one trading
   day, reads Kite's one-minute candles through the existing candles parsing (ADR-066: internal use only), applies the
   W-062 finalize rule through the store, refuses before the session close (BSE/NSE close per the existing session
   rules), and is a no-op on a day already final (second run changes nothing). No scheduling on any host (deploy work).
4. **Tests** (expected values from the fixtures, never from running the code): the contract; the replay comparison
   PG vs in-memory bar by bar after an engine dispose; finalize on `tests/fixtures/kite_history/candles-2026-10-08.json`
   (every compared minute equals Kite's candle, source kite; the 15:09 gap minute final from Kite; second run: 0 rows
   changed); refuse-before-close; a failing store never raises into the recorder's caller (REQ-051 AC-5).

## Reviewer checklist (each must turn a test red)
- Store a price as float; allow UPDATE of a final day; finalize twice changes rows; finalize before close runs;
  PG store returns a different bar than the in-memory store for the same input; a store error propagates to the feed.

## Rules (this PC also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted tests only. DB, from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-067 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<your files>`;
  alembic via the same runner: `python -m alembic -c backend/ofo_app/alembic.ini upgrade head` (ofo_test is at 0008);
  leave the DB at your 0009 head. Domain: `python -m pytest -q -p no:cacheprovider tests/history` (one directory per call).
  CI mirror: `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-067 W-067 --no-tests`.
  Never the full app suite, Playwright, npm or ci_local.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views; read them with Read/Grep.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified. Push `build/W-067-history-pg`.
