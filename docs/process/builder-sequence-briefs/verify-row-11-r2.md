# Verifier brief: builder sequence row 11 (REQ-114 / W-139), Tier A, ROUND 2 - FINDINGS ONLY (ADR-178 (1))

Independent, adversarial verifier; you did not build this and you did not run round 1. READ-ONLY: never edit, create,
commit or delete a tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\verify-11r2`.

Scope (ADR-178 (1)): re-check ONLY round 1's findings and the files the fix changed. Do not re-run all eight criteria.
The fix touched no money, order or auth file not seen in round 1, so no full re-check.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (row 11's
fix 1 = commits 38b757fe and cffc1da8, merged into the chunk branch). Round 1 brief: `verify-row-11.md`; the fix brief
with the findings and attack list: `docs/process/builder-sequence-briefs/row-11-fix-1.md`. Spec: `spec/requirements/REQ-114.md`
AC-2, AC-6, AC-7 (as amended by ADR-177), ADR-119.

Files the fix changed (read only these and their tests): `backend/ofo_app/live_market.py`,
`backend/ofo_app/routes/broker_status.py`, `backend/ofo_app/kite_ws.py`, `backend/ofo/marketdata/disconnect.py`,
`backend/ofo/errors/templates.py`, `backend/ofo_app/catalogue_refresh.py`, `frontend/e2e/feed-reconnect.spec.ts`,
`tests/marketdata/test_feed_health.py`, `tests/marketdata/test_market_closed_wording.py`,
`tests_app/test_broker_status_route.py`, `tests_app/test_kite_ws.py`, `tests_app/test_kite_ws_silence.py`,
`tests_app/test_live_feed_status.py`.

Check, each with a pass/fail and file:line:
1. AC-7 (was MAJOR): `feed_phase()` passes `market_open` from the ADR-119 calendar at the INJECTED clock (not the wall
   clock); the route reads a closed market as closed in every phase except ENDED; Sat 2026-10-24 10:00 and holiday
   2026-10-20 10:00 with the socket backing off read market closed; Wed 2026-10-21 10:00 backing off reads reconnecting;
   the 5-minute reconnect floor is unchanged. One mutant: force `market_open=True` in `feed_phase` - a test must fail.
2. ADR-177 wording: one text "Market closed. Prices are from <time>." in the backend (disconnect.py, templates.py) with
   the same characters as `marketClosedText` in `frontend/src/lib/sharedStateText.js`; grep (loosely: quotes, case) for
   the old "last price" wording anywhere a user sees it.
3. AC-2 (MINOR, mutant A10): remove `provider.on_disconnected` from `kite_ws._dropped` in a scratch copy - a test in
   `tests_app/test_kite_ws_silence.py` must fail.
4. AC-6 (MINOR): `_is_token_error` matches only session-token errors (TokenException, access-token message); "Invalid
   instrument token 123" keeps reconnecting with back-off; an unknown error text never loops. Both cases tested.
5. The e2e regex accepts only the new "Reconnecting - prices as of" text.

Database: do NOT run the app DB suite; CI on draft PR #525 runs it and the orchestrator classifies those results. You
may run at most ONE DB file locally (for mutant A10), only through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini -o faulthandler_timeout=60 tests_app/test_kite_ws_silence.py`
(it holds the one database lock; waiting is correct). Mutants via `python scripts/orchestrator/mutation_gate.py`,
results to your scratch folder.

Why Opus: Tier A - `backend/ofo_app/live_market.py`, `backend/ofo_app/kite_ws.py` and the broker status route are live
feed files in the safety set (a closed market or a dead socket shown as live prices).
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per check: `{"row": 11, "req": "REQ-114", "ac": "AC-n", "result": "pass" | "fail" |
"partial", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 200 words: each fail/partial
with severity and the smallest fix, and anything not checked.
Reference: none - searched reconnect, disconnect, market closed, last close (ADR-177: market-closed wording is NO-SCREEN; COPY records go to the chunk-1 copy builder, ADR-178 (2)). Open records RD-039, RD-046, RD-047, RD-065, RD-066, RD-068 are NOT judged in this round: they are built by the chunk-1 reference-copy builder.
Tests: python -m pytest -q -p no:cacheprovider tests/marketdata; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 15 min wall-clock, 20 tool calls
Report: evidence-table
