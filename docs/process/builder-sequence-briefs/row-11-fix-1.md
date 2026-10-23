# Row 11 fix round 1: REQ-114 (W-139) - the market-closed state is shown, the drop is pinned, a token error is a token error

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on every guard you add or move before reporting; write the results to a
file in your scratch folder and quote it (R18).
Size: M, 10 files, 5 items
CI: app tests job (`tests_app/test_live_feed_status.py`, `tests_app/test_broker_status_route.py`, `tests_app/test_kite_ws_silence.py`, `tests_app/test_kite_ws.py`; vars: DATABASE_URL via the throwaway-database runner); kit tests job (`tests/marketdata/`; vars: none); frontend job (`frontend/e2e/feed-reconnect.spec.ts`).
Expected (orchestrator, before dispatch, clock 13:28 read from `date`): 45 min / ~220k. Verify round 2 after it is the last round.

Core: on a closed market (Sat 2026-10-24, and the 2026-10-20 holiday) a socket that is silent or backing off is shown
as market closed with the banner text, never as "reconnecting".
Proof: step 1 is a failing test on the REAL functions: `live_market.feed_phase()` and the broker status route at an
injected clock of Sat 2026-10-24 10:00 IST with the socket in back-off -> today the phase is RECONNECTING and the row
reads reconnecting (row 11 verify r1, AC-7 MAJOR); after the fix the phase is FEED_MARKET_CLOSED and the text is
"Market closed. Prices are from <time>." with the last price's server time in IST.

Spec basis: REQ-114 AC-7 (amended by ADR-177): outside market hours "the screens read "Market closed. Prices are from
<time>." (the shared banner text, ADR-177)" and no reconnect more often than once every 5 minutes. REQ-114 AC-2 (the
drop marks the quotes stale and the feed disconnected), AC-6 (a token error or a 403 ends the session, never retried in
a loop). ADR-119 (market calendar). ADR-015 (no stale data shown as live).
Copy from: none.
Reference: catalogue 010-039 - copy nothing new here: the reference product shows only a prices-updated clock; its
watchdog numbers already match (bundle-findings 6.1); market-closed wording is NO-SCREEN (ADR-177; searched reconnect,
disconnect, market closed, last close).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next`, branch `build/seq-row-11`, head b04d47f0. FIRST merge the
chunk branch into it: `git merge --no-edit build/seq-chunk-1` (brings ADR-177 and the amended REQ-114; only spec and
docs files, no overlap with the row). Commit with `git commit -F <msg> -- <your paths>`; do NOT push. BINDING: never
stop a process by name; stop only PIDs you started. Database tests ONLY through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-next python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 <files>`
(it waits for the one database lock; another run may hold it - waiting is correct). Frontend mutants: copy `frontend/`
to your scratch folder and run vitest THERE, never swap files inside the worktree (R4). Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\row11-fix1`.

## What to do
1. MAJOR AC-7: `backend/ofo_app/live_market.py` `feed_phase()` passes `market_open=is_market_open(<the injected
   clock>)` (the ADR-119 calendar, `market_calendar.is_market_open`); `backend/ofo_app/routes/broker_status.py` reads a
   closed market as closed in EVERY phase except ENDED (a socket backing off on a weekend reads market closed) and
   renders the market-closed text with the last price time; the 5-minute reconnect floor is unchanged.
2. One wording (ADR-177): `market_closed_message` (`backend/ofo/marketdata/disconnect.py`) and the template text in
   `backend/ofo/errors/templates.py` become "Market closed. Prices are from <time>." - the same characters as the
   frontend's `marketClosedText` (`frontend/src/lib/sharedStateText.js`, which stays the frontend's one home). Grep the
   whole repo (backend, tests, tests_app, frontend) for the old "last price" wording and update every user-facing use.
3. MINOR AC-2: in `tests_app/test_kite_ws_silence.py` assert that the drop marks the provider disconnected
   (`connected is False`) and the phase RECONNECTING during back-off (kills verifier mutant A10: removing
   `provider.on_disconnected` from `kite_ws._dropped`).
4. MINOR AC-6: `_is_token_error` (`backend/ofo_app/kite_ws.py:83`) matches only a token error of the session -
   `TokenException` or an access-token message - not "Invalid instrument token 123"; a test for both.
5. Small: `backend/ofo_app/catalogue_refresh.py:10` comment no longer says "no calendar"; `frontend/e2e/feed-reconnect.spec.ts`
   regex accepts only the new "Reconnecting - prices as of" text, not the row 9 text.
Then: run the R13 selection for the row's whole backend diff through the runner (the row 11 verifier's database run
had about 10 failures, unclassified, log `...\b9b5cb32-...\scratchpad\verify-11\db-run.log`). For each failure, run
it on fb9a3702 (a temp worktree, plain `git worktree remove` after): fails there too -> list it as pre-existing; passes
there -> it is this row's and you fix it.

Attack list: (each names its test file)
1. Sat 2026-10-24 10:00 IST, socket in back-off -> phase market closed, row text "Market closed. Prices are from <time>." (`tests_app/test_live_feed_status.py`).
2. Holiday 2026-10-20 10:00 -> market closed; Wed 2026-10-21 10:00 with the socket backing off -> reconnecting (`tests_app/test_broker_status_route.py`).
3. The drop marks the feed disconnected and the phase RECONNECTING; mutant A10 killed (`tests_app/test_kite_ws_silence.py`).
4. "Invalid instrument token 123" does NOT end the session; a TokenException frame does (`tests_app/test_kite_ws.py`).
5. Every user-facing market-closed text is the ADR-177 wording; the old wording appears nowhere a user sees it (`tests/marketdata/` text test + grep quoted).
6. The e2e reconnect test fails on the row 9 text (`frontend/e2e/feed-reconnect.spec.ts`).

Standing items: (a) n/a: no time-budgeted job changes; (b) n/a: no CI step changes; (c) the token check is an allow-list of the session-token error shapes and fails safe (an unknown error text keeps reconnecting with back-off, never a loop); (d) the calendar's answer states - open, closed by hours, weekend, holiday, a date with no calendar data (2027) - each with what the status row shows.
Threat model: in scope - a closed market shown as reconnecting, a silent socket shown as live, an instrument error ending a user's session; out of scope - the calendar's own data (row 11 part A, unchanged).
Findings checked: wall-clock-assertion-flakes-under-load, guard-as-forbidden-list, dependent-tests-not-run-stale-later
Reviewer checklist: the real feed_phase and route at an injected clock; one wording, its characters asserted; A10
killed; token check narrowed with both cases tested; pre-existing failures proven on fb9a3702; gate results quoted; no
new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
