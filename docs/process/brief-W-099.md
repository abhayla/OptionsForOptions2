# Builder brief: W-099 Circuit bands from Zerodha's quote - the one gate input ENTRY still lacks in production (Tier A: a door on the Kite allow-list)

Core: Zerodha's real REST quote of 2026-10-16 15:07:20 for NIFTY26O1923650CE (instrument token 12080386; the
`quote` object in `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/fetch.json`) comes back through ONE new
allow-listed door call, `GET /quote?i=NFO:NIFTY26O1923650CE`, as the exact Decimal band lower 0.05, upper 81.55 for
that contract; a price of 3.35 is inside it, 81.60 outside (`ofo.execution.price_check.circuit_block`).
Proof: step 1 is `tests_app/test_kite_quote_bands.py::test_core_real_quote_gives_the_band` on a fixture built from
that real quote (wrap it as Kite's REST reply `{"status": "success", "data": {"NFO:NIFTY26O1923650CE": <quote>}}`;
README line naming the source file and that the envelope is ours). Write it FIRST, red.

Tier: A (a new call on the Kite allow-list, REQ-073 AC-4). Model: sonnet.
Budget: 40 min wall-clock, 44 tool calls. HARD limit: at call 41 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words, plus each guard and its
killing test (mutation-run).
Copy from: none - spec/technical-design/legacy-reuse.md has no quote-band row we may reuse (searched: quote, circuit);
the door pattern is this repo's `backend/ofo_app/kite_reads.py` (W-093).
Findings checked: guard-as-forbidden-list, money-parsed-through-float, secret-filter-by-key-name,
repo-wide-scan-outside-targeted-tests, caller-supplied-verdict-trusted
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

Read first: `docs/process/builder-brief.md`, `CLAUDE.md`, `backend/ofo/broker/kite_endpoints.py`,
`backend/ofo/broker/kite_http.py`, `backend/ofo_app/kite_reads.py` and `tests_app/test_kite_reads.py` (copy their
shape), `backend/ofo/execution/price_check.py`, `backend/ofo/execution/safety.py` `_price_failures` (how
`ExecutionContext.price_bands` is read: keyed by `product_key(leg)`, a `(lower, upper)` pair).

## Spec basis
- ADR-080: "a price outside the day's circuit band blocks that leg with the reason, never a silent clamp"
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."

## Work card (commit FIRST as `work/W-099.md`, frontmatter shape of `work/W-091.md`) and coverage row
id W-099; title "Circuit bands from Zerodha's quote for the pre-execution gate (ADR-080; GET /quote door)";
requirement_ids [REQ-073]; tier A; status in_progress; depends_on [W-093]; tests_required
['AC-4: tests_app/test_kite_quote_bands.py']; core/proof = the lines at the top. Add `W-099: 4b` under `work_items:`
in `docs/process/coverage-stages.yaml`.

## What to build
1. `ALLOWED_CALLS["ofo_app/kite_reads.py"]` gains exactly `("GET", "/quote")` (a read; the door must accept the
   query string `i=...` repeated, as Kite's API takes it, and nothing else - check how `check_call` treats queries).
2. `KiteReads.fetch_circuit_bands(instruments: Sequence[str]) -> dict[str, tuple[Decimal, Decimal]]`, keyed by the
   `EXCHANGE:TRADINGSYMBOL` the caller asked for; parse with `parse_float=Decimal`; each `lower_circuit_limit` /
   `upper_circuit_limit` exact (a JSON integer stays exact; a float never). Fail closed per instrument: missing key,
   non-numeric, lower > upper, lower or upper <= 0 -> that instrument is ABSENT from the result (the gate then blocks
   an ENTRY leg as band-unknown, ADR-080), never a guessed band; a whole-reply failure -> `KiteReadError(code)` as in
   W-093. At most the instruments asked for; an extra key in the reply is ignored, never added.
3. Do NOT wire it into the Execute route (round 3 of W-095 is editing that file; the wiring is the next step after
   both land). Expose only the client method.

## Reviewer checklist (each red when mutated; write these first)
- `("GET", "/quote")` changed to any write, or a second path added -> `tests/test_no_order_placement.py` /
  your exact-entry test red.
- `parse_float=Decimal` removed -> red. Lower > upper accepted -> red. A missing instrument given (0, inf) or any
  default -> red (it must be absent).
- The access token never in repr / log / exception (reuse W-093's test shape).

## Rules
- Targeted tests: `python -m pytest -q -p no:cacheprovider tests/test_no_order_placement.py tests/test_kite_http_guard.py tests/errors/ tests/test_*.py tests/engine/test_pricing_scan.py`
  and `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_quote_bands.py tests_app/test_kite_reads.py tests_app/test_kite_http_guard.py tests_app/test_egress_gate_doors.py`
  (no database). `python scripts/ruff_ratchet.py` must not rise. Never run `atool.py` and nothing against a database.
- No route, no UI, no migration. No kit or `spec/` edit, no `views/`, no regenerated files, no `evidence/`.
- Commit and push `build/W-099-quote-bands`. No PR.
