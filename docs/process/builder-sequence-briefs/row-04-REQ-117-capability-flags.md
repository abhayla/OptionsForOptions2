# Row 4: REQ-117 Broker capability flags (W-132, builder sequence chunk 1, Tier A, size M: ~10 files)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: a feature asks a named flag, and a missing, unknown or unloadable flag hides it with a plain reason.
Proof: step 1 is a failing test: remove `basket_margin_quote` from the Zerodha flag set -> the margin line is hidden
with a plain reason (today it always shows); then the same with an unknown name and with a flag source that fails to
load.

Spec basis: REQ-117 AC-1: "The broker interface (REQ-054 AC-1) exposes a fixed set of named flags, at least - basket
page orders, broker-held triggers, intraday product, order-update stream, funds read, positions read, basket margin
quote." REQ-117 AC-2: "The Zerodha implementation sets each flag with the Zerodha source and date it rests on (ADR-016
consequence); the broker-held trigger flag stays off until REQ-100 AC-1's core proof has passed." REQ-117 AC-3: "A repo test
fails if feature code compares a broker name or id (for example "zerodha") instead of a flag." REQ-117 AC-4: "A flag that is
missing, unknown or fails to load counts as off (fail closed); a test removes one flag and shows the feature hidden,
not shown." REQ-117 AC-5: "Flags never loosen a safety gate: margin, reconciliation block, market hours, kill switch and
freeze-limit checks run the same whatever a flag says."
Copy from: none - the legacy-reuse map has no REQ-117 row (copy_from_check.py finds none); OpenAlgo's per-broker
capability file is a REFERENCE idea under REQ-054 (ideas only, AGPL).
Sensibull: keys features on broker flags such as MIS supported (REQ-117, its Why paragraph).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (checked out). Commit with
`git add <your paths>` (never `-A`: other agents share the tree); do NOT push; no PR. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row04`.

## Measured starting state (2026-10-22, head after row 3)
Nothing of REQ-117 exists: no flag code in backend/ or frontend/. `KiteBrokerReader` (`backend/ofo_app/kite_broker_reader.py`,
row 3) has only fetch methods. Broker-name comparisons exist in data-layer code (`catalogue_store.py:216,302,505,582,609`
`ref.broker == ZERODHA`, `ofo/instruments/eligibility.py:240`, `reconciliation_store.py:208`): per-broker tables keyed
by broker, legitimate. UI text names Zerodha (`MarginLine.vue:20` "Margin (Zerodha)", `chainUnavailable.js:7`).
REQ-100 (stop at Zerodha), REQ-102 (MIS) and REQ-103 (Orders page, funds view) do not exist yet.

## What to build (orchestrator decisions, technical)
1. `backend/ofo/broker/capabilities.py`: a closed enum of the seven flags (names: `basket_page_orders`,
   `broker_held_triggers`, `intraday_product`, `order_update_stream`, `funds_read`, `positions_read`,
   `basket_margin_quote`); each value is (on/off, source, date as `datetime.date`); a value without a source or date is
   refused at load; `is_supported(flags, name)` answers False for a missing or unknown name and for a set that failed
   to load (never raises to a caller).
2. Zerodha's values, each with a source and date (one module or data file, loaded by the reader):
   `basket_page_orders` on (Kite publisher basket, ADR-054); `broker_held_triggers` OFF until REQ-100 AC-1's core proof
   (source: REQ-100 AC-1 not passed, 2026-10-22); `intraday_product` on (source: the real profile reply
   `tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json`, products include MIS); `order_update_stream`
   on (Kite Connect order postbacks / WebSocket order updates docs); `funds_read` on (`GET /user/margins`, row 3);
   `positions_read` on (`GET /portfolio/positions`, row 3); `basket_margin_quote` on (`POST /margins/basket`,
   `kite_margin.py`). Cite each source as a URL or repo path with the date 2026-10-22.
3. The reader exposes the flags (`KiteBrokerReader.capabilities`), and the `BrokerReader` protocol gains it.
4. Read-only route `GET /api/broker/capabilities` (ApiModel response, registered in the response door list and
   openapi) giving each flag's on/off only (no source text needed by the browser); one frontend module reads it once.
5. One real consumer now: the builder's margin line is shown only when `basket_margin_quote` is on; off -> hidden with
   the plain reason "Margin from the broker is not available for this account." (no broker name in the reason). The
   features REQ-100/102/103 bind their flags when they are built (orchestrator records AC-3's feature part as deferred).
6. Repo test (`repo_scan`): feature code = `backend/ofo_app/routes/`, `backend/ofo/strategy/`, `backend/ofo/outcome/`
   and `frontend/src/` excluding text/labels files; it fails on a comparison of a broker name or id (`== "zerodha"`,
   `== ZERODHA`, `in (...)` with a broker string, JS `===`/`includes`, `'kite'`) and fails closed on a file it cannot
   parse. Data-layer modules (catalogue, eligibility, reconciliation stores, the broker adapter) are outside by path.
7. AC-5: a test runs the margin gate, the reconciliation block, the market-hours check, the kill switch and the
   freeze-limit check with every flag on and every flag off and asserts identical outcomes (the gates never read flags).

Attack list: (the final verifier runs each; run each yourself first, row-review R1)
1. Remove one flag from the Zerodha set -> the dependent feature (margin line) hidden with the reason, not shown.
2. Ask an unknown flag name -> off, no exception, no truthy default.
3. Flag data fails to load / malformed / None / a value missing its source or date -> every flag off (fail closed).
4. Plant `broker == "zerodha"` (and `'kite'`, the `ZERODHA` constant, `in (...)`, JS `===`) in feature code -> the
   repo test red; the same text in a data-layer module -> green.
5. `broker_held_triggers` is off for Zerodha and nothing reads it as on.
6. Every flag on vs every flag off -> margin, reconciliation block, market hours, kill switch, freeze limit identical.
7. The hidden-feature reason names no broker; a request or the client cannot change a flag (route is GET-only, no
   query parameter changes the answer).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the broker-name scan names its scope
by path, discovers files from the tree and fails closed on a file it cannot parse; (d) n/a: flags are our own
declared data, no other system's answer is read at runtime (sources are cited, not fetched).
Threat model: in scope - a feature shown when its flag is missing or unknown, a feature keyed on a broker name, a flag
that loosens a safety gate; out of scope - a forged flag object injected at runtime (ADR-098).
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: closed enum asserted exactly; fail-closed tests for missing/unknown/unloadable/source-less; the
scan's attack variants each red; AC-5 identical outcomes asserted per gate; openapi regenerated and the door list
updated; every guard has a test that dies without it (mutation list in the report, scratch copies only); every changed
test file run in full, DB files through the main checkout's db_run.py with 0 skipped; no new duplicated literal; reuse
the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (except
openapi.json).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus every changed test file in full and `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `market_data/{symbol_converter,token_manager,instrument_query,ticker_base,failover_fetch,factory}.py`, other-broker adapters, `app/models/broker_instrument_tokens.py` | SKIP | cross-broker mapping/failover, platform-wide token; keyed on a Zerodha symbol string with converters for 2 of 6 brokers (spec/findings.md F-09); our identity is (exchange, exchange_token) per ADR-050 | REQ-054 |
| `tests/fixtures/record_broker_responses.py`, `record_raw_responses.py`, `record_websocket_ticks.py` | ADAPT | recorder pattern for Kite fixtures; recorded upstox files carry PII: never copy | REQ-054 |
| `services/brokers/kite_adapter.py` (584) | ADAPT | row 4; Decimal in; floats only at the SDK edge (`:163,168,218,220,326`), private to the transport | REQ-054, REQ-060 |
