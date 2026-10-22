# Row 3: REQ-054 Broker adapter, read part (W-131, builder sequence chunk 1, Tier A, size M)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: one Zerodha broker reader, reached only through the Kite door, answers the AC-1 read calls from REAL Kite replies.
Proof: step 1 is the account read through the door; the orchestrator then runs it once against the owner's live
session and commits the redacted reply as the fixture; your converter test runs on that real reply (the recorded
`/portfolio/positions` and `/orders` fixtures already in `tests/fixtures/` cover the other reads).

Spec basis: REQ-054 AC-1: "A broker interface offers: authenticate, fetch account, fetch margin, fetch positions, fetch
orders, build an order basket for the user to place on the broker's own page (ADR-054; the adapter never places orders
through the API, except for the one stop-loss module of REQ-100/REQ-101 named in REQ-073 AC-4, ADR-162), fetch order
status, reconcile." REQ-054 AC-2: "Only the Zerodha implementation exists in V1; no unused broker implementations are
built." In scope here: the READ parts of AC-1 (authenticate, fetch account, fetch margin, fetch positions, fetch orders,
fetch order status) and AC-2. Basket and reconcile are order-path parts, deferred by the contract (ADR-165). AC-3 and
AC-4 are built (measure 2026-10-22) and are only re-verified, not changed.

Copy from: legacy-reuse map rows 2 and 4 (ADAPT: `services/brokers/base.py` order/position/quote types + BrokerAdapter;
`kite_adapter.py` Kite to unified converters, Decimal fields), rows 98-99 (the same files with line notes); REFERENCE:
OpenAlgo plugin layout (ideas only, AGPL); SKIP: market_data symbol converters (keyed on a Zerodha symbol, F-09). The
local algochanakya checkout is READ ONLY.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (the orchestrator creates
it from main before dispatch). Commit on that branch as you go; do not push; do not open a PR. Scratch folder:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row03`.

## Measured starting state (main 235e1793)
Built: authenticate (`ofo/broker/kite_auth.py`, `ofo_app/kite_client.py`), margin (`kite_margin.py:172,179`), raw
positions/orders reads (`kite_reads.py:196,208`) and their converters (`kite_replies.py:272,332,346`). Protocol
`BrokerReader` (`ofo/execution/partial.py:164`) has NO Kite implementation (only the test fake
`tests/execution/partial_inputs.py:132`). Missing: account read, order-status read, the Kite reader, an AC-2 test.

## What to build
1. Account read: add `GET /user/profile` to `ALLOWED_CALLS` (`ofo/broker/kite_endpoints.py`) and a reader method in
   `kite_reads.py` beside the others, through the same door. The domain value keeps ONLY `user_id`, `broker`,
   `exchanges`, `products`, `order_types` (closed key set; any other key ignored and never stored or logged: the reply
   carries name, email and avatar). Decision (orchestrator, technical): no caching, no DB write.
2. Order status: decided from the ONE `/orders` list call (already allowed), never `/orders/{id}` per order
   (technical call: one request instead of N, REQ-118 rate limits). `fetch_order_statuses(ids)` returns, per asked id,
   the status of that order's row; an id absent from the list -> an explicit not-found state, never a default.
3. `KiteBrokerReader` implementing `BrokerReader` (all four methods) over the existing reads and converters: no second
   copy of a converter, header or parse helper (reuse them).
4. AC-2 test: an allow-list of broker implementation modules (exactly the Zerodha/Kite ones), discovered from the
   source tree, asserted exactly; a scratch module named like another broker must turn it red.

Every Kite answer state for each new read (standing item d): stated (normal reply), empty list, `status: error` with
each Kite exception type the door already maps (TokenException, PermissionException, NetworkException, InputException,
GeneralException), HTTP 429, timeout, malformed JSON, a missing required key, an unexpected extra key. Each maps to the
door's existing refusal codes; nothing raises a raw exception to a route; no retry (CLAUDE.md hard rule).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the AC-2 detector discovers modules
from the source tree and fails closed on a module it cannot classify; (d) every Kite answer state above listed and tested.
Threat model: in scope - a new Kite call not on the allow-list, PII from the profile reply reaching a log, a response or the DB, a missing order id silently read as a status; out of scope - a forged code object injected at runtime (ADR-098).
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: exact closed key set on the profile value with a test that adds an `email` key and asserts it is
absent from the value and the log; not-found order id test; 429/timeout/malformed tests; no duplicated helper; every
guard has a test that dies without it (mutation list in the report); no new duplicated literal; reuse the existing
helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the changed files' tests (domain directly; app files through `python scripts/orchestrator/db_run.py . python -m
pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`) and `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `market_data/{symbol_converter,token_manager,instrument_query,ticker_base,failover_fetch,factory}.py`, other-broker adapters, `app/models/broker_instrument_tokens.py` | SKIP | cross-broker mapping/failover, platform-wide token; keyed on a Zerodha symbol string with converters for 2 of 6 brokers (spec/findings.md F-09); our identity is (exchange, exchange_token) per ADR-050 | REQ-054 |
| `tests/fixtures/record_broker_responses.py`, `record_raw_responses.py`, `record_websocket_ticks.py` | ADAPT | recorder pattern for Kite fixtures; recorded upstox files carry PII: never copy | REQ-054 |
