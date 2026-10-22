# W-1xx: Four indices from the instrument file, daily fresh list, eligibility read (REQ-090, REQ-053 read part)

Common brief: docs/process/builder-brief.md (read it first; this file is the item part only).

Core: BANKNIFTY and FINNIFTY resolve strike gap, lot size and expiries from the day's real Zerodha file, never from a literal.
Proof: load the recorded real instrument files in D:\Abhay\Ventures\competitors\sensibull\2026-10-21\raw\kite-instruments\ (NFO and BFO, read only, copied into tests/fixtures/ with a source note) through the real parser (backend/ofo/instruments/parser.py) and assert BANKNIFTY gap 100 / lot 30 and FINNIFTY gap 50 / lot 60 / monthly expiries only, read from the file.

Tier: A (strike gap, lot size, expiry list and the contract eligibility read feed every price, quantity and band)

Spec basis:
REQ-090 AC-1: "can be selected as underlyings everywhere an underlying is chosen"
REQ-090 AC-2: "are read from the day's instrument and exchange files (ADR-052, ADR-104), never typed"
REQ-090 AC-3: "is an admin setting like ADR-042's"
REQ-090 AC-4: "never offers a shape or quick pick that needs a weekly or later expiry it does not have"
REQ-090 AC-5: "is streamed and health-checked on the platform feed exactly as REQ-072 does for NIFTY 50 and SENSEX"
REQ-090 AC-7: "gains BANKNIFTY and FINNIFTY cases from recorded real files, never fixtures typed from memory"
REQ-053 AC-2: "The contract catalogue (what exists) is stored separately from current eligibility (what Zerodha permits)"
REQ-053 AC-3: "Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are currently unavailable"

Copy from: (1) parked PR #459 (branch gc6/instr-fresh): `INSTRUMENT_LIST_PUBLISH_IST`, `database_list_stamp`, `get_list_stamp`, the freshness rule 'stamp on today's IST date AND at or after 08:30 IST' (backend/ofo/timeutil.py) and tests/execution/test_instrument_list_freshness_gate.py; copy the rule and the stamp seam, NOT the Execute route wiring. (2) legacy-reuse.md row 10 (instrument_master.py, BFO/SENSEX handling only; our parser already exists). (3) parked #455 trading-day calendar is already on main as backend/ofo/market_calendar.py.

Sensibull screens: builder underlying picker and Ready-made tab 010-039; preset-matrix.md (38 strategies x NIFTY, BANKNIFTY, FINNIFTY, SENSEX: legs, strikes, lot sizes); Option Chain 060-067 header (underlying search, expiry list 27 Oct ... 30 Mar). FINNIFTY calendar server error noted in REQ-090 source: reproduce nothing, refuse with a catalogue message.

Multi-broker review (read D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md first): L4 (one instrument per broker row: REQ-054 AC-3 keys the broker token to the contract identity) and trap T7 (never key instruments on a built symbol string nor wipe and reload the table daily) and T3 (lots vs units: quantities are units everywhere).

## What to build
1. Underlying list from the catalogue (backend/ofo/instruments/catalogue.py, sources.py), never a typed tuple of four names where a catalogue row can say it: add an `exchange` per underlying (NFO for NIFTY, BANKNIFTY, FINNIFTY; BFO for SENSEX), recorded (REQ-001 AC-4). Every picker (builder, chain, guided flow, watchlist) reads it (AC-1). Routes: backend/ofo_app/routes/catalogue.py, indices.py, chain.py.
2. REQ-075 AC-1 repo test: extend it so a lot-size or strike-gap literal for any of the four indices outside its home module fails (AC-2). Find it with Grep 'REQ-075' in tests/.
3. Scenario column step for BANKNIFTY and FINNIFTY as an admin setting like ADR-042's (backend/ofo/admin/); default decided from the real strike list and written as a decision row BEFORE build (AC-3): see Open: technical.
4. Monthly-only underlyings: a shape or quick pick needing a weekly or later expiry is refused with a plain catalogue message, never a 500 (AC-4). Example: FINNIFTY calendar spread with one monthly expiry listed.
5. Spot index for NIFTY BANK and NIFTY FIN SERVICE streamed and health-checked exactly as NIFTY 50 / SENSEX (backend/ofo_app/index_push.py:52 index_ids, routes/indices.py) (AC-5); stale = 'unavailable'.
6. Daily fresh list: a callable `refresh_instruments()` built on backend/ofo_app/catalogue_load.py and the #459 freshness rule; the worker lane (D1, REQ-115) schedules it after 08:30 IST. Contracts are never deleted when unavailable (REQ-053 AC-2); eligibility is stored apart from the catalogue (backend/ofo_app/eligibility_from_zerodha.py exists).
7. Builder leg add checks eligibility from Zerodha data and blocks unavailable legs (REQ-053 AC-3, the part before a leg is added; the 'repeat before execution' half is out of scope).
8. Per-underlying tests gain BANKNIFTY/FINNIFTY from recorded files (AC-7). REQ-090 AC-6 (Execute blocked until freeze and charge tables) is out of scope: Execute is off.

## AC status (main plus open PRs, 2026-10-21)
| AC | Status | Where |
|---|---|---|
| 090 AC-1 | missing | BANKNIFTY/FINNIFTY only in backend/ofo_app/kite_replies.py symbol parsing |
| 090 AC-2 | partial | parser reads the file (backend/ofo/instruments/parser.py); no four-index home-module test |
| 090 AC-3 | missing | |
| 090 AC-4 | missing | |
| 090 AC-5 | missing | index_push.py:52 index_ids covers two |
| 090 AC-6 | out of scope | Execute off |
| 090 AC-7 | missing | |
| 053 AC-2 | exists | catalogue 0003-0005 migrations, eligibility.py |
| 053 AC-3 | partial | W-120 (PR #466, branch gc6/w118-sel) adds selection plus per-contract permission: land first or stack on it |
| freshness | parked #459 | copy as above |

## Every answer state of each outside system
Instrument file (Kite): downloaded today after 08:30 IST (stated) = fresh. Downloaded before 08:30 or on an earlier date (stale) = Execute-style gate is not needed here, but the builder shows 'instrument list not from today' and quick picks refuse. Missing/naive/future stamp (absent) = fail closed, same message. File lacks FINNIFTY rows (not found) = underlying not offered. Empty file (empty) = keep yesterday's catalogue and mark stale, never wipe (trap T7). Download fails (failed) = keep the catalogue, alert via the worker lane. Duplicate contract token across segments (ambiguous) = refuse the load. Database: load runs in one transaction; a failed load leaves yesterday's rows (findings daily-load-misses-intraday-additions, daily-list-trims-far-strikes-trips-truncation-guard).

## Attack cases (reviewer: hands-on first)
- A test that types 'lot 30' for BANKNIFTY in app code fails the repo scan; deleting the scan makes the test red.
- File where BANKNIFTY lot changes between days: the new lot is used, no cached literal.
- FINNIFTY calendar spread: catalogue message, HTTP 4xx, never 500.
- Load stamp 08:29 IST today: not fresh; 08:30:00: fresh; tomorrow 00:01 with yesterday's stamp: not fresh.
- SENSEX (BFO) contract identity not mixed with NFO tokens (finding instrument-identity-keyed-on-one-broker).

Threat model: in scope: wrong stamp, truncated or duplicated file, typed literals; out of scope: a malicious Zerodha file (trusted source, validated by the parser).

Findings checked: daily-load-misses-intraday-additions, daily-list-trims-far-strikes-trips-truncation-guard, freshness-judged-on-request-start-clock, request-clock-for-database-stamped-fact, instrument-identity-keyed-on-one-broker, fixture-symbol-not-in-catalogue, aggregate-across-mixed-instrument-kinds

Standing items: (a) applies: the refresh job runs inside the worker's budget; it uses its own small slot and a test shows the higher-priority monitor job still runs. (b) n/a: no CI step added. (c) applies: the literal scan names the home module by import source and fails closed on re-exports. (d) applies: states above.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests/instruments/, tests_app/test_catalogue_*.py, tests_app/test_execute_catalogue_stale.py is parked: do not copy; tests_app/test_indices*.py, tests/test_market_calendar.py, plus every file naming 'NIFTY' lot or gap literals
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception: a changed API model regenerates docs/api/openapi.json and is registered in tests_app/test_response_door.py, per builder-brief.md).
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: AC-3 default scenario step for BANKNIFTY and FINNIFTY. Proposal: derive it from the real strike list as 2x the strike gap (BANKNIFTY 200, FINNIFTY 100), recorded as a decision row before build, as ADR-157 requires; the decision-row write is a spec edit, done in this PR's item part per spec-first R4.
Open: technical: merge order. Depends on #466 (selection) landing in Step 1; #459 is parked and stays parked: copy only.
Open: business: none. Live window needed for: AC-5 spot streaming of the two new indices (owner Kite login).

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `tests/backend/instruments/test_instrument_master.py` | ADAPT | as test cases for our catalogue persistence | REQ-053 |
| `app/utils/tradingsymbol.py` (63) | REFERENCE | catalogue is the one source of symbols | REQ-053 |
| `services/brokers/market_data/ticker/index_token_maps.py` (42) | REFERENCE | hardcoded tokens; use the catalogue | REQ-053 |
| `market_data/kite_adapter.py` (440) | ADAPT | user's own session token only, server-side | REQ-048, REQ-053 |
| `market_data/{symbol_converter,token_manager,instrument_query,ticker_base,failover_fetch,factory}.py`, other-broker adapters, `app/models/broker_instrument_tokens.py` | SKIP | cross-broker mapping/failover, platform-wide token; keyed on a Zerodha symbol string with converters for 2 of 6 brokers (spec/findings.md F-09); our identity is (exchange, exchange_token) per ADR-050 | REQ-054 |
| `tests/fixtures/record_broker_responses.py`, `record_raw_responses.py`, `record_websocket_ticks.py` | ADAPT | recorder pattern for Kite fixtures; recorded upstox files carry PII: never copy | REQ-054 |
| `services/brokers/kite_adapter.py` (584) | ADAPT | row 4; Decimal in; floats only at the SDK edge (`:163,168,218,220,326`), private to the transport | REQ-054, REQ-060 |
