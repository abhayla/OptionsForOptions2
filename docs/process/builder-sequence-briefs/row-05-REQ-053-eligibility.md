# Row 5: REQ-053 Contract eligibility, read part (W-133, builder sequence chunk 1, Tier A, size M: ~7 files)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).
Expected (row-review): ~90 min / ~450k tokens (measure 1 + build 60 + verify 20 + orchestrator 10).

Core: the catalogue the add-time check reads is today's Zerodha list, refreshed during the trading day.
Proof: ALREADY RUN by the orchestrator on real data, 2026-10-22 13:31 IST: `python -m ofo_app.catalogue_load` on ofo_dev
loaded today's Kite list (`added=4 seen=4974 revised=0 newly_unlisted=0 retired=0 delisted=0 reinstated=0`); before it
the newest load was 2026-10-21, and a save at 10:08 IST today passed against that stale list. Step 1 for you: a failing
test that an add-time check against a list whose latest load is not today's India date (database clock) answers
`gate_contract_unconfirmed`, then the scheduler.

Spec basis: REQ-053 AC-3: "Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are
currently unavailable; the check repeats just before execution." (the before-execution repeat is order-path scope,
deferred). REQ-053 AC-5: "Any Zerodha rule encoded in code (market-order limits, SL-M limits on index options,
freak-trade protection, OI and strike restrictions, basket execution) cites a current Zerodha source and date; 'options
are limit-only' is never hard-coded." REQ-053 F-33 (2026-10-08): "a once-a-day catalogue load misses strikes listed
after it ran". AC-1, AC-2, AC-4 are built (measure 2026-10-22) and are re-verified, not changed.
Copy from: legacy-reuse map rows for REQ-053, appended below by copy_from_check.py (act on each).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (checked out). Commit with
`git add <your paths>` (never `-A`); do NOT push; no PR. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row05`.

## Measured starting state (2026-10-22, head 239c9c19)
Built: sealed eligibility from Zerodha's list (`ofo/instruments/eligibility.py`), separate catalogue with guarded
`apply_update` (`catalogue_store.py:470,541`), add-time check `_check_eligible` (`routes/strategies.py:287`, used at
:330/:360/:387), pickable contracts only (`catalogue_picker.py:65-83`), fresh registry read side
(`eligibility_from_zerodha.py:92`). Missing: `catalogue_load.py:12` "No scheduler" (nothing runs the load); no intraday
refresh (F-33, finding `daily-load-misses-intraday-additions`); no test of a list loaded twice in a day; no AC-5
citation check (`sources.py` holds some source rows; read it).

## What to build (orchestrator decisions, technical)
1. Staleness: the add-time check (and the picker's offer) treats a catalogue whose latest successful load is not
   today's India date on the database clock as unconfirmed -> `gate_contract_unconfirmed`; a load earlier today is
   current. `TEST_CATALOGUE_DATE` (test-only pin) keeps working.
2. Scheduler: one in-process asyncio task in the app lifespan, started only when a setting `CATALOGUE_REFRESH=1` (and
   on by default when `LIVE_MARKET=1`): a load at start-up, then every 60 minutes between 08:15 and 15:45 IST on
   trading days (reuse the project's exchange trading-day calendar if one exists - grep `trading_day`, `holiday`,
   ADR-119 - else every weekday, and say so); each run calls the existing `catalogue_load.run` path unchanged (every
   guard applies); never two runs at once; a failure (network, refusal) logs its code only, keeps the previous list,
   and the next run retries on schedule (that is not an automatic order retry); the task stops cleanly on shutdown.
   Kite's instrument list is a public URL: confirm the loader's fetch goes through the project's egress door.
3. Intraday additions (F-33): a test loads a real list, then the same real list with extra real rows (take them from
   `tests/fixtures/instruments/instruments_slice.csv`: hold back some rows on the first load, add them on the second)
   -> the additions appear, nothing duplicates, one history revision where a term changed, and a contract held back
   then added is offered by the picker after the second load.
4. AC-5: a repo test (`repo_scan`): every module constant that encodes a Zerodha rule (market-order limits, SL-M,
   freak-trade, OI/strike restrictions, basket limits, freeze, lot) sits next to a source citation with a URL or doc
   name AND a date, discovered by a name/shape rule you define and document; and no code says options are limit-only
   (grep shapes: `limit_only`, `LIMIT_ONLY`, `only LIMIT`, an options branch forcing order_type LIMIT). It fails closed
   on a file it cannot parse.

Attack list: (the final verifier runs each; run each yourself first, row-review R1; each names its test file)
1. Add-time check against a list last loaded yesterday -> `gate_contract_unconfirmed`; loaded earlier today -> eligible
   (`tests_app/test_eligibility_from_zerodha.py`).
2. A list loaded twice in a day with held-back real rows added the second time -> additions offered, no duplicates
   (`tests_app/test_catalogue_store.py` or a new `tests_app/test_catalogue_refresh.py`).
3. Scheduler: two runs never overlap; a failing run keeps the old list and logs the code; no run outside 08:15-15:45
   IST or on a non-trading day; shutdown stops the task (`tests_app/test_catalogue_refresh.py`, fake clock).
4. An expired contract still present in the list (F-33: 398 expired SENSEX rows on 08-Oct) -> refused; one expiring
   today -> offered (`tests/execution/test_eligibility_from_zerodha_list.py`).
5. A truncated list (> 10% of an index, or > half of one expiry) from the scheduler path -> refused, nothing written,
   previous list kept (`tests_app/test_catalogue_refresh.py`).
6. A Zerodha rule constant planted without a source and date -> the AC-5 scan red; a planted `LIMIT_ONLY` for options
   -> red; the real tree -> green (`tests/test_zerodha_rules_cited.py`).
7. Token 61746 reused after expiry -> the retired row never shadows the live one after a scheduled reload
   (`tests_app/test_contract_identity_lifecycle.py`).

Standing items: (a) the scheduler is a time-budgeted job: each run has a timeout, and a test shows a slow or hung load
never blocks the live feed or a request (the higher-priority work still runs); (b) n/a: no CI step changes; (c) the
AC-5 scan names its scope by path, discovers files and fails closed on a file it cannot parse; (d) Kite's list answer
states: full list, empty file, truncated file, HTTP error, timeout, a malformed row, a list for the wrong date - each
listed and tested (refuse and keep, never half-write).
Threat model: in scope - a leg saved against a stale or truncated list, an intraday strike never offered, a Zerodha rule
hard-coded without a source; out of scope - a forged instrument list served from a hijacked Kite host (TLS is the
transport's job).
Findings checked: daily-load-misses-intraday-additions, guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: staleness on the database clock (never the app clock); the scheduler reuses `catalogue_load.run`
unchanged; every answer state tested; every guard has a test that dies without it (scratch-copy mutation list); every
changed test file run in full, DB files through the main checkout's db_run.py with 0 skipped (known failing, not yours:
#497 empty-catalogue asserts); grep for the old answer of anything changed with the hit count; no new duplicated
literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus every changed test file in full and `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `tests/backend/instruments/test_instrument_master.py` | ADAPT | as test cases for our catalogue persistence | REQ-053 |
| `app/services/instrument_master.py` (414) | REFERENCE | row 10; our W-006 parser already exists: take BFO/SENSEX handling only | REQ-053 |
| `app/utils/tradingsymbol.py` (63) | REFERENCE | catalogue is the one source of symbols | REQ-053 |
| `services/brokers/market_data/ticker/index_token_maps.py` (42) | REFERENCE | hardcoded tokens; use the catalogue | REQ-053 |
| `market_data/kite_adapter.py` (440) | ADAPT | user's own session token only, server-side | REQ-048, REQ-053 |
