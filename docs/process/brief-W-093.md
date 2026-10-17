# Builder brief: W-093 Kite read door - orders / trades / positions (Tier A: a door on the Kite allow-list)

Core: the recorded real replies of the owner's 2026-10-16 order (`tests/fixtures/kite_replies/orders-122104.json`,
`trades-122104.json`, `positions-122104.json`) come back through ONE new door client as exact-Decimal `data`, and
`ofo_app/kite_replies.py` turns them into 1 order (tag OFS1V1L0, filled 65), 1 fill (trade 4484194) and a 65-unit
position for NIFTY26O1923650CE.
Proof: step 1 is `tests_app/test_kite_reads.py::test_core_recorded_entry_replies_through_the_door` with a replay
transport serving those three files byte for byte. Write it FIRST, red.

Tier: A (a door on the Kite allow-list, REQ-073 AC-4). Model: sonnet.
Budget: 45 min wall-clock, 50 tool calls. HARD limit: at call 46 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no Kite read-client row we may reuse (searched: orders,
positions, trades); algochanakya's kite adapter is not copied (ADR-054). Pattern to follow: `backend/ofo_app/kite_margin.py`.
Findings checked: guard-as-forbidden-list, money-parsed-through-float, broker-reply-shape-unproven-at-domain-boundary,
secret-filter-by-key-name, caller-supplied-verdict-trusted, targeted-tests-miss-dependent-files
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py

Read first: `docs/process/builder-brief.md` (the common brief: every line applies), `CLAUDE.md`,
`backend/ofo/broker/kite_endpoints.py`, `backend/ofo/broker/kite_http.py`, `backend/ofo_app/kite_margin.py` (copy its
door, transport, token-in-header-only and error-code style), `backend/ofo_app/kite_replies.py`,
`tests/test_no_order_placement.py`, `tests/test_kite_http_guard.py`, `tests_app/test_kite_http_guard.py`,
`tests_app/test_kite_margin_client.py`, `tests/fixtures/kite_replies/README.md`.

## Spec basis
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from
  Zerodha and reconciles them (REQ-057, REQ-060)"
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."
- REQ-073 (AC-4 clarification): "Every module that calls Kite is named in the allow-list with its calls"

## Work card (commit FIRST as `work/W-093.md`; copy the frontmatter shape of `work/W-091.md`)
id W-093; title "Kite read door: GET orders / trades / positions through one allow-listed client (REQ-073 AC-3/AC-4)";
requirement_ids [REQ-073]; tier A; status in_progress; depends_on []; affected [backend/ofo/broker/, backend/ofo_app/,
tests/, tests_app/]; tests_required ['AC-3: tests_app/test_kite_reads.py', 'AC-4: tests/test_no_order_placement.py'];
core / proof = the two lines at the top of this brief; review_status 'not reviewed'; next_action 'Tier A review'.

## What to build
1. `ALLOWED_CALLS` gains ONE new module entry, `"ofo_app/kite_reads.py"`, with exactly three reads:
   `("GET", "/orders")`, `("GET", "/trades")`, `("GET", "/portfolio/positions")`. Nothing else changes in that file.
2. `backend/ofo_app/kite_reads.py`: class `KiteReads(*, api_key, access_token, transport=urllib_transport,
   base_url=KITE_API_URL)` with `fetch_orders() -> list`, `fetch_trades() -> list`, `fetch_positions() -> Mapping`
   returning the reply's `data` parsed with `json.loads(text, parse_float=Decimal)`. Reuse kite_margin's transport
   type, URL constant, header building and error mapping (import them; do not copy; if a helper is private, make it
   public in kite_margin.py rather than duplicating it). Fail closed with `KiteReadError(code)`: non-200, transport
   error, non-JSON body, `status` not `"success"`, `data` of the wrong type (orders/trades must be a list, positions a
   mapping with `net` and `day` lists). Codes `kite_read_token` (403/TokenException) / `kite_read_busy` (429) /
   `kite_read_refused` (other 4xx) / `kite_read_unavailable` (5xx, network, junk) / `kite_read_bad_reply`. The token
   is only in the Authorization header; never in a log line, repr or exception (assert it).
3. Tests `tests_app/test_kite_reads.py` (no database): the core proof above (feed the parsed `data` into
   `kite_replies.orders_from_reply` / `fills_from_reply` / `positions_from_reply` with
   `ContractIndex.from_instrument_slice(instruments-2026-10-16-slice.json)` - assert tag `OFS1V1L0`, filled 65, trade
   id `4484194`, net `{key: 65}`); the 151006 files give a flat position (`net == {}`); the same rows as JSON numbers
   (live REST shape) give equal Decimals; every error code; the request method and path the transport saw are exactly
   the allow-listed ones.

## Reviewer checklist (each red when mutated; write these first)
- Add `("POST", "/orders/regular")` to the new entry -> `tests/test_no_order_placement.py` goes red (prove it in a
  scratch copy; do not commit the mutation).
- Change one path to `/orders/` + anything, or the method to POST -> the door refuses before the transport is called.
- `parse_float=Decimal` removed -> a test with JSON-number money goes red (`Decimal("5.1")`, not `5.1` float).
- `status: "error"` with HTTP 200 -> `kite_read_bad_reply`; positions `data` without `net` -> `kite_read_bad_reply`.
- The access token string appears nowhere in `repr(client)`, the exception text, or captured log output.
- Every guard you write has a killing test; list them in the report.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/test_no_order_placement.py tests/test_kite_http_guard.py tests/marketdata/ tests/test_*.py`
  and `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_reads.py tests_app/test_kite_http_guard.py tests_app/test_kite_margin_client.py tests_app/test_egress_gate_doors.py`
  (no database needed; if a file needs one, skip it and say so). Grep `tests/` and `tests_app/` for `ALLOWED_CALLS`
  and `kite_endpoints` and add every file that names them. Then `python scripts/orchestrator/atool.py <your worktree> W-093 --no-tests`
  and read its exit and every ` rc ` line; `python scripts/ruff_ratchet.py` must not rise.
- No route, no UI, no migration, no change to `kite_replies.py` behaviour. No kit or `spec/` edit, no `views/`, no
  findings INDEX, no regenerated files. Never write `evidence/`.
- Commit and push `build/W-093-kite-reads`. No PR.
