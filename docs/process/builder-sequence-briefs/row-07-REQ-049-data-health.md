# Row 7: REQ-049 Data health (W-135, builder sequence chunk 1, Tier A)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; every changed test file in
full; fix lint as you go, no bulk noqa). Expected (row-review, set 16:50 IST before dispatch): ~90 min / ~450k tokens
(measure 1.5 + build 60 + verify 20 + orchestrator 10).
Size: M, 11 files, 3 items
CI: kit tests job (`tests/marketdata/*`, `tests/broker_name_allowlist.py`; vars: none); app job `api` step
(`tests_app/test_live_feed_status.py`, `tests_app/test_execute_health_clock.py`; vars: TEST_DATABASE_URL only - run them
locally with `env -u DATABASE_URL` through the throwaway-database runner).

Core: the live data-health answer counts only price ticks the platform asked for, and after market hours it never
tells the user to reconnect.
Proof: step 1 is a failing test on the recorded frames (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`):
after the last screen releases its tokens, a frame carrying only unwanted ticks still calls `on_data`
(`kite_provider.py:77-78`, issue #513 item 1; live measurement 2026-10-22: Connected for ~3 s after the last screen
closed).

Spec basis: REQ-049 AC-2 and AC-4 (read `spec/requirements/REQ-049.md` in full; quote each AC you change in your
report). ADR-015 (no stale data shown as live). Finding F-32 (spec/findings.md: a contract with no tick for 60 s on
a healthy feed is not stale). Issue #513 (row 2's deferred MINORs, assigned to this row).
Copy from: legacy-reuse map rows for REQ-049, appended below by copy_from_check.py (act on each; the legacy 2026
holiday list is wrong - F-54 - never copy it).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. DB tests:
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`.
Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row07`.

## Measured starting state (2026-10-22, head 150873d3)
Built: normalised fields (`quote.py`, `health.py:98`), the five health states (`health.py:52`, `feed_health.py:94`),
the disconnect message (`marketdata/disconnect.py`, `errors/templates.py:446`), per-strategy availability
(`availability.py:27`, `LiveStrategyCard.vue:119-121`). Partly: AC-3 trigger records store `data_health`
(`timeline/records.py:57,123,143`) - check the rules path refuses to fire on a non-AVAILABLE quote; AC-4 screens show
stale legs but have no after-hours wording.

## What to build (orchestrator decisions, technical)
1. #513 item 1: `on_data` only when the frame carries at least one tick for a token that is currently wanted; a frame
   of only unwanted/released ticks counts as connection activity at most, never as live data.
2. #513 item 2: `get_kite_session` (`routes/execute.py:161-162`) logs the exception CLASS (never its text, never a
   token) when a stored session cannot be read, then refuses as today.
3. #513 item 3 + AC-4: outside market hours the live-data row and the Settings text never advise Reconnect; they say
   the market is closed and live prices resume at the next open. Reuse the ONE existing market-hours check
   (`routes/execute.py` `market_open`, around line 242) - move it to a shared module if needed, never write a second
   one; no holiday calendar exists (say so; F-54 forbids the legacy list). Update the pinned text in
   `tests/broker_name_allowlist.py` if it changes. Also confirm AC-3: the rules/trigger path refuses on a
   non-AVAILABLE quote (add the test if missing).

Attack list: (each names its test file)
1. Released tokens, then a frame with only unwanted ticks -> the live row goes idle on time, `on_data` not called
   (`tests/marketdata/test_pipeline_stages.py` or `tests/marketdata/test_feed_health_replay.py`).
2. A frame with one wanted tick among unwanted ones -> counts as live data (same file).
3. A heartbeat alone -> never healthy (`tests/marketdata/test_feed_health_replay.py`).
4. A quiet contract on a healthy feed for 60 s -> not stale (F-32; same file).
5. An unreadable stored session -> one log line with the exception class, no token or message text
   (`tests_app/test_execute_health_clock.py`, caplog).
6. A fixed clock at 15:29, 15:31, 09:14, 09:15 IST on a weekday and 11:00 on a Saturday -> the advice text is
   Reconnect only inside market hours (`tests_app/test_live_feed_status.py`).
7. A trigger evaluated on a STALE quote -> does not fire, and the record shows the health (`tests/marketdata/test_rule_health.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) the
feed's answer states: wanted tick, only unwanted ticks, heartbeat only, no frame, socket in backoff, session ended,
market closed - each gives a defined row and text.
Threat model: in scope - a status claiming live data from unwanted ticks, Reconnect advice after hours, a token in a log; out of scope - a wrong exchange holiday (no calendar exists yet).
Findings checked: keepalive-counted-as-live-data, first-live-frame-before-first-price, wall-clock-assertion-flakes-under-load
Reviewer checklist: real recorded frames for items 1-4; one market-hours check reused; fixed clocks, no wall-clock
asserts; every guard has a test that dies without it (scratch-copy mutation list); every changed test file in full,
with CI's variables only; no new duplicated literal; reuse the existing helper; ruff baseline must not rise; targeted
tests only; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `app/utils/market_hours.py` (138) | ADAPT | add holiday calendar and BSE hours; its hard-coded 2026 holiday list is wrong (F-54): never copy it, use the dated NSE data file (ADR-119) | REQ-049 |
| `services/brokers/market_data/ticker/models.py` (84) | ADAPT | row 1; fix float serialization `:61-69` | REQ-049 |
| `src/services/priceService.js` (251) | ADAPT (P3b) | polling fallback only; change math from the backend | REQ-049 |
| `src/components/common/MarketStatusBanner.vue`, `DataSourceBadge.vue` | ADAPT (P3b) | data-health indicator | REQ-049 |
