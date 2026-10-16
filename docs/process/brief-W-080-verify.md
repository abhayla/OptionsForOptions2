# Verifier brief: W-080 read-only Kite basket (Tier A)

Core: a 4-leg iron condor plan on the real 2026-10-15 contracts (NIFTY26O1923150CE, NIFTY26O1923350CE,
NIFTY26O1922750PE, NIFTY26O1922550PE) produces a basket of 4 LIMIT orders, NFO, quantity 65, `readonly: true`,
symbols from the catalogue row matched to exactly one row, 4 distinct tags (<= 20 alphanumeric) decoding to the same
strategy; the basket build calls the freeze and margin gates itself; no code path can place an order through Kite's
API (refused at runtime before sending, plus a static second layer).
Proof: re-run and attack yourself; the builder's report and the reviews are claims. This is the item's last gate: a
FAIL parks it.

Model: opus (Tier A verifier).
Budget: 30 min wall-clock, 30 tool calls. HARD: at call 27 stop and return what you have.
Report: evidence-table, then the JSON block below (one block per AC).

## Where
- Your own read-only copy: `git -C D:/Abhay/Ventures/OptionsForOptions2 worktree add --detach <scratchpad>/v080 origin/build/W-080-kite-basket`;
  remove it at the end from the main checkout.
- Brief + checklist: `docs/process/brief-W-080.md`; card `work/W-080.md`; REQ-073; ADR-054, ADR-060, ADR-090; F-22; the
  saved Kite docs page `docs/research/kite-basket-docs-2026-10-16.html` (on the branch).
- ACs and fingerprints (main checkout, `python tools/ac_fp.py REQ-073 <AC> --yaml`): AC-1 `ad9b88fb2d53`, AC-2
  `12b126ca3e41`, AC-4 `acbaab536416`.

## Spec basis
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order"
- REQ-073 AC-2: "Every order in the basket carries our own tag (at most 20 alphanumeric characters) that identifies the strategy
    and plan version, so the result is matched by tag, never by symbol"
- REQ-073 AC-4: "No code path places an order through the order-placement API; a test fails if one is added."

## Check (how could it fail?)
1. In `v080`, separately: `python -m pytest -q -p no:cacheprovider tests/execution`, `tests/orders`,
   `tests/test_no_order_placement.py`, and `tests/test_door_names_private.py tests/test_fixture_symbols.py`; app (targeted):
   `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <scratchpad>/v080 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_http_guard.py tests_app/test_kite_login.py tests_app/test_broker_token_store.py tests_app/test_kite_history.py`.
2. AC-1: build the condor basket in a probe (outside the repo); compare every field with the docs page and with the real
   request legs in `docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json`; prices serialize without
   float artefacts.
3. AC-2: tag length/charset/uniqueness; parse_tag round trip; refusal (not truncation) when ids do not fit. Note the known
   gap: plan version is a caller integer (ExecutionPlan has no version; deferred #263) - judge whether AC-2 still holds.
4. AC-4: from a client built by the guarded constructors (`backend/ofo_app/kite_http.py`) and the urllib door
   (`backend/ofo/broker/kite_http.py`), attempt POST /orders/regular, PUT/DELETE /orders/regular/1, POST /gtt/triggers,
   a relative "orders/regular" on a base_url client, `..`/percent-encoded paths, another *.kite.trade host - each refused
   before sending (use httpx.MockTransport / a fake opener; no network). Plant a passed-in client in a temp module and run
   the static test against it. Confirm allowed reads still pass.
Never write in the main checkout; never write `evidence/`.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-1", "requirement": "REQ-073", "ac_fp": "...", "result": "pass|fail", "commands": "...", "observed": "...", "attack": "..."},
 {"ac": "AC-2", ...}, {"ac": "AC-4", ...}]
```
Plus defects (file:line, severity).
