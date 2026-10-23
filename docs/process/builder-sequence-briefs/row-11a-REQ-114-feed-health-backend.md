# Row 11 part A (backend): REQ-114 feed health check and reconnect, price socket part (W-139)

Row-ahead: yes (ADR-171: built while row 10 is verified; closes after row 10)
Overlap: none (checked against row 10 REQ-118's files: backend/ofo/broker/rate_limit.py, ofo/broker/kite_http.py,
ofo_app/kite_http.py, kite_endpoints.py, kite_reads.py, kite_margin.py, kite_history.py, kite_client.py,
ofo/instruments/downloader.py, ofo_app/order_limits_registry.py, the errors templates, tests_app/test_rate_limit_door.py,
tests/broker/test_rate_limit.py, tests_app/test_kite_reads.py, tests_app/test_kite_margin_client.py,
tests/test_kite_http_guard.py - none of them is touched here; the new constants go in a NEW module, never in
order_limits_registry.py; if you find you must touch any listed file: STOP, commit, report)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, commit, report; scratch
mutations; R13-R18; run `python scripts/orchestrator/mutation_gate.py` once it exists on your branch).
Size: M, 11 files, 5 items
CI: kit tests job (`tests/marketdata/test_reconnect_policy.py`, `tests/test_market_calendar.py`,
`tests/test_market_calendar_validation.py`, `tests/marketdata/test_feed_health.py`; vars: none); app job `api` step
(`tests_app/test_kite_ws_silence.py`, `tests_app/test_kite_ws.py`, `tests_app/test_kite_ws_resubscribe.py`; vars:
TEST_DATABASE_URL, REDIS_URL). NO DATABASE RUN in this part (ADR-171 rule 4: row 10 holds the one slot) - run only
tests that need no database; the DB-backed selection runs after the rebase, by the orchestrator's schedule.
Expected (orchestrator, before dispatch): build 60 min / ~170k; verify 20 min / ~170k (after row 10 closes).

Core: a Kite socket that stays open but sends nothing for 60 s is closed and reconnected with capped, jittered
back-off, and its quotes stay stale until a fresh tick after the reconnect.
Proof: step 1 is `tests_app/test_kite_ws_silence.py` failing first: the REAL `KiteSocket` against a fake socket that
plays the recorded frames (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`) then goes silent; on the
injected clock, at 60 s it closes and reconnects; the subscriptions are re-sent; quotes read stale until the first
replayed frame after the reconnect.

Spec basis: REQ-114 AC-1: "Every 15 s each connection checks the time of its last frame of any kind (a tick or the
broker's heartbeat)." REQ-114 AC-2: "After 60 s with no frame the connection is closed and reconnected". REQ-114 AC-3:
"capped at 30 s, each with random jitter of up to 50% of the wait". REQ-114 AC-7: "Outside market hours (ADR-119
calendar) silence is expected". F-32 (no tick for 60 s on one contract is not staleness). F-54 (the legacy holiday list
is wrong; the project's list is the dated NSE file). ADR-119 (the holiday list is dated data with a source).
Copy from: legacy-reuse row `app/utils/market_hours.py` (ADAPT: session logic only, never its holiday list, F-54) - the
ADAPTED version already exists on branch `gc6/mkt-hours-reread` (cd7dd5ba): take `backend/ofo/market_calendar.json`,
`backend/ofo/market_calendar.py`, `tests/test_market_calendar.py`, `tests/test_market_calendar_validation.py` from it
with `git checkout gc6/mkt-hours-reread -- <those four paths>` (contract reuse rule: only these files, never a merge).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next` (made by the orchestrator with wt-new.ps1), branch
`build/seq-row-11`, from the chunk head. Work, test and commit ONLY there; never read-write the main sequence worktree
(row 10's). Commit with `git add <paths>` / `git commit -F <msg> -- <paths>`; do NOT push. Scratch:
`...\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row11a`.

## What to build (orchestrator decisions, technical)
1. `backend/ofo/marketdata/reconnect_policy.py` (new, standard library): the constants CHECK_EVERY 15 s, SILENT_AFTER
   60 s, BACKOFF start 1 s doubling cap 30 s (move `kite_ws.BACKOFF_START/BACKOFF_MAX` here and import them back), jitter
   up to 50% of each wait from an injected `random.Random`, CLOSED_RETRY_EVERY 5 min; each with its REQ-114 AC as the
   source. Pure functions; a seeded test asserts the sequence bounds (AC-3).
2. `kite_ws.py`: a silence watchdog on the CONNECTION's last frame of any kind (tick or 1-byte heartbeat, never one
   contract's tick age - F-32): checked every 15 s, at 60 s close and reconnect, quotes stale from that moment (AC-2);
   `on_connected` only AFTER every subscription is re-sent (AC-4: today `:110` fires before the subscribe at `:113`); a
   token-error text frame after connect ends the session like a 403, no retry loop (AC-6); the backoff resets only on
   the first DATA frame, never on a bare connect (no storm).
3. Market closed (AC-7): wire the calendar - `ofo.timeutil.market_open` becomes the calendar's `is_market_open` (one
   check; every caller of `market_open` named and its tests run - R15/R13); outside market hours the feed state reads
   "market closed - last price <time>" (text in the errors templates' one home) and reconnects at most once per 5 min.
4. Logs (AC-8): every disconnect, reconnect attempt and recovery logged with the user ref, the reason and the
   timestamps, never the token (extend the existing log-secret test).
5. `feed_main.py`: pass the user ref to each socket (for the logs).
The browser part (AC-5 "Reconnecting - prices as of <time>") is part B (frontend), a separate brief.

Attack list: (each names its test file)
1. Quiet contracts but heartbeats arriving -> no reconnect (`tests_app/test_kite_ws_silence.py`).
2. 59.9 s vs 60.0 s of total silence on the injected clock (same file).
3. Seeded jitter within 0-50% of each wait; the 30 s cap holds (`tests/marketdata/test_reconnect_policy.py`).
4. A drop before the first data frame does not reset the back-off (same silence file).
5. `on_connected` fires only after the subscribe is sent; quotes stale until a fresh tick (`tests_app/test_kite_ws_resubscribe.py`).
6. A token-error text frame or a 403 on reconnect ends the session, no retry (`tests_app/test_kite_ws.py`).
7. A weekend and the 2026-10-20 holiday: market closed, at most one reconnect per 5 min (`tests/marketdata/test_feed_health.py`, `tests/test_market_calendar.py`).
8. Logs carry user and reason, never the token (`tests_app/test_kite_ws.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) n/a: no static detector; (d) Kite's socket answer states - data frame, heartbeat, text frame (order update, token error, other), close, 403 at connect, connect refused, silence - each listed in `tests_app/test_kite_ws_silence.py` or `test_kite_ws.py` with what it does.
Threat model: in scope - a silent socket shown live, a reconnect storm, a reconnect loop on a dead session, a token in a log, a holiday read as open; out of scope - NSE changing its holiday list mid-year (the file's fetch date says when it was read).
Findings checked: wall-clock-assertion-flakes-under-load, dependent-tests-not-run-stale-later, guard-as-forbidden-list
Reviewer checklist: silence measured on the connection; constants in the new module only; on_connected after the
re-subscribe; calendar file taken from gc6/mkt-hours-reread unchanged except where a test proves a defect; every
market_open caller named; no DB run; mutation results to a file (R18); no new duplicated literal; reuse the existing
helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
