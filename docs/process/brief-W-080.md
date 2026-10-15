# Builder brief: W-080 read-only Kite basket from the execution plan (Tier A)

Core: a 4-leg iron condor plan on the real 2026-10-15 contracts (NIFTY26O1923150CE, NIFTY26O1923350CE,
NIFTY26O1922750PE, NIFTY26O1922550PE) produces a basket of 4 orders: exchange NFO, those trading symbols looked up by
InstrumentId, LIMIT, quantity 65, `readonly: true`, 4 distinct tags of at most 20 alphanumeric characters that decode
to the same strategy and plan version.
Proof: step 1 is `tests/execution/test_kite_basket.py`, expected exchange/symbol/side/quantity taken from the request
legs of `docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json` (a real request Kite accepted).
Write it FIRST, red.

Tier: A (order path). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD limit: at call 60 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md maps algochanakya's order adapter as SKIP/blocked for API placement (ADR-054); no basket row exists.

Read first: `docs/process/builder-brief.md`, `work/W-080.md`, `spec/requirements/REQ-073.md`, `spec/decisions/ADR-054.md`,
`spec/decisions/ADR-060.md`, `spec/decisions/ADR-090.md`, `spec/findings.md` F-22 (~line 261), the execution plan code
(`backend/ofo/execution/` planner / `sequence.py` / `review.py`), the order book tags (`backend/ofo/orders/model.py`
`next_client_tag` ~434), the catalogue identity and per-broker table (`backend/ofo/instruments/catalogue.py`,
`ref(ZERODHA)`), issue #115 (`gh issue view 115`), `CLAUDE.md`.

## Spec basis
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order"
- REQ-073 AC-2: "Every order in the basket carries our own tag (at most 20 alphanumeric characters) that identifies the strategy
    and plan version, so the result is matched by tag, never by symbol"
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."
- REQ-054 AC-3: "a contract with no row for a broker cannot be traded
    at that broker - no symbol is guessed or derived"

## What to build
1. Save Kite's documentation page as the source: `curl -sL https://kite.trade/docs/connect/v3/basket/ -o
   docs/research/kite-basket-docs-2026-10-16.html` (if it fails, say so; then build to F-22's facts only). Read the
   form target, form fields and per-order JSON keys from it; quote them in the module docstring.
2. Domain (`backend/ofo/execution/basket.py`, standard library): `build_basket(plan, catalogue, strategy_id,
   plan_version) -> KiteBasket` - orders in plan order; each order: exchange + trading symbol from the contract's
   ZERODHA row (by InstrumentId; a contract with no row -> refuse the whole basket with the catalogue error, never a
   partial basket), transaction type, quantity (units), order type LIMIT, price (Decimal, as the plan holds it, already
   tick-rounded upstream - do not round here), product NRML for entries, variety regular, `readonly: true`, tag.
   Serialize to the JSON the form needs with prices as decimal strings/numbers exactly as the docs show (no float
   artefacts: 3.95 must serialize as 3.95).
3. Tag: deterministic, alphanumeric only, at most 20 characters, unique per order within the basket, and decodable back
   to (strategy id, plan version, leg index) by a pure `parse_tag`; a round-trip test over generated ids; refuse ids
   that cannot fit (fail closed, never truncate silently).
4. AC-4 guard `tests/test_no_order_placement.py`: scans `backend/` sources for any call path to Kite's placement
   endpoint (`/orders/` with POST/PUT, `place_order`, `modify_order`, `kiteconnect` order methods) and fails if one
   exists; an allow-list test proves the scan catches a planted example (generated in a temp dir, never committed).
   Keep `send_guard.py` as is; note in the report that `_Transport.submit -> broker order id` has no place in the basket
   path (the orchestrator files it).
5. #115 for this path only: the basket and its tags carry the InstrumentId; nothing new keys on the trading symbol.
6. The basket build CALLS the gates itself, never trusting a caller's verdict (W-076 Tier A review MAJOR 2): the
   freeze check (W-076's `freeze.py` via its store->review adapter, limits from the store, lot from the catalogue) and
   the margin gate (W-081's `margin_gate.check_margin`). If those modules are not on `main` when you start, define the
   two gate calls behind small protocol parameters (`freeze_check`, `margin_check`) that `build_basket` must receive
   (required, no default) and test with fakes that a blocked freeze or margin result refuses the whole basket.

## Reviewer checklist (write first; each red when mutated)
- Order of orders != plan order -> red. A MARKET order or missing `readonly` -> red.
- Symbol derived/concatenated instead of looked up -> red (a catalogue row whose symbol differs from the derived form).
- Missing broker row for one leg -> the whole basket refused.
- Tag: 21 characters or a non-alphanumeric character -> red; two legs with the same tag -> red; parse_tag round trip.
- Placement scan catches a planted `requests.post(<base>/orders/regular)` and `kite.place_order(`.
- Float price in the output -> red.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/execution tests/orders tests/test_no_order_placement.py`.
  No database. Then your worktree's own `scripts/orchestrator/atool.py <worktree> W-080 --no-tests`.
- No route, no UI, no migration. Do not edit the freeze review block, the charges code or the executable-price code
  (parallel items). No kit or `spec/` edit, no `views/`, no findings INDEX. Never write `evidence/`.
- Commit and push `build/W-080-kite-basket`. No PR.
