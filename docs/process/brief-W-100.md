# Builder brief: W-100 Circuit bands into the Execute route - the last production input ENTRY lacks (Tier A: order path)

Core: the Execute route's ENTRY fills `ExecutionContext.price_bands` from Zerodha's real quote through
`KiteReads.fetch_circuit_bands` (W-099): with the recorded quote `tests/fixtures/kite_replies/quote-150720.json`
(band 0.05 / 81.55) served by the replay transport, `test_core_real_order_entry_then_exit` stays green WITHOUT the test
seam that supplied a band; a quote reply missing the contract -> the ENTRY leg refused `gate_price_band_unknown`.
Proof: `tests_app/test_execute_route.py` on the real test DB once (main's head 0016), through the main checkout's
`db_run.py` with your worktree as cwd.

Tier: A (the order path). Model: sonnet.
Budget: 35 min wall-clock, 40 tool calls. HARD limit: at call 37 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 200 words, `git status --short` empty,
each new guard with its killing test (mutation-run).
Copy from: none - wiring between two merged items (W-095 route, W-099 door).
Findings checked: caller-supplied-verdict-trusted, repo-wide-scan-outside-targeted-tests, fallback-time-claims-missing-data
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- ADR-080: "a price outside the day's circuit band blocks that leg with the reason, never a silent clamp"

## Build
1. In `backend/ofo_app/routes/execute.py`, after the legs are known and before the gate: one call
   `fetch_circuit_bands([f"{exchange}:{tradingsymbol}" ...])` (off the event loop, like the route's other Kite calls),
   mapped to `price_bands` keyed by `product_key(leg)`; an instrument absent from the result stays absent (the gate
   blocks an ENTRY leg, warns on an EXIT - existing rules). A whole-reply `KiteReadError` -> no bands at all (same).
2. Remove the test seam that supplied bands from outside Zerodha (keep the quote/depth seam). Tests: the recorded
   quote gives the band; a reply without the contract -> `gate_price_band_unknown` for ENTRY; EXIT still proceeds
   with a band (inside) and is blocked only by a price outside a known band.
3. Before push, each as its own command: `python -m pytest -q -p no:cacheprovider` (the full domain suite, ~3.5 min,
   no DB), `python scripts/ruff_ratchet.py`, the route's non-DB tests; then the ONE DB run; then
   `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2 python -m alembic -c backend/ofo_app/alembic.ini current`
   (must print main's head).

## Rules
- Branch `build/W-100-band-wiring` from origin/main (#359 and the W-099 PR merged). Work card `work/W-100.md`
  (frontmatter shape of `work/W-091.md`; requirement_ids [REQ-073]; tier A; depends_on [W-095, W-099];
  tests_required ['AC-1: tests_app/test_execute_route.py']) and `W-100: 4b` in `docs/process/coverage-stages.yaml`.
- Never copy .env; never atool.py; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`.
