# Verifier brief: row 19 backend part (W-147, REQ-080 leg picker reads) - Tier A checker

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing; scratch copies for every mutation. No database over the tunnel (the DB tests run in CI on draft PR #531).
Why Opus: `backend/ofo/marketdata/kite_provider.py` is in the safety set (SAFETY_SET in scripts/orchestrator/measure_process.py).

Spec basis: REQ-080 AC-2 "IV and delta come from the engine"; REQ-080 AC-5 "No stale price is shown as current
(ADR-015)"; REQ-080 AC-6 "for each option expiry, the forward level the engine prices that expiry with"; REQ-080 AC-7 "5
levels of bid and ask with quantities"; REQ-080 AC-8 "with the reason, never an empty or old table".
Copy from: build/W-124-a3-chain backend/ofo/engine/chain_values.py (taken in this row)
Reference: screens 024, 031, 032, 033, 034, 035, 130, 131, 244, 245 - copy only what each open record says; open RD-032, RD-129, RD-130, RD-131, RD-132, RD-133, RD-134

What was built (chunk head d88a7354 on `build/seq-chunk-2`, worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`;
row 19 commits 43b8bebb, 9e8fdd82, 3b42b86d, ae0327e7): `backend/ofo_app/routes/leg_picker.py` (strikes, futures,
depth reads), `backend/ofo/engine/chain_values.py` (IV and delta per strike), `kite_frames.py` (day values and last trade
time decoded), `provider.py` / `kite_provider.py` / `feed_health.py` (`latest_day_stats` and `futures_quote` on the
provider interface, futures from the platform's own feed), `main.py` (router; `# noqa: PLR0915` added on create_app).
Scope now: the backend reads only (REQ-080 AC-1, AC-2, AC-5, AC-6, AC-7, AC-8 at the route); AC-3 and AC-4 (picker
buttons, lots and quantity mode) and the screen parts are the row's frontend part, checked later.

For EVERY AC say which route shows it and whether you exercised it THERE (ASGI client on the recorded replay
`OUTCOME_REPLAY`/fixtures under `tests/fixtures/kite_ws/`, or the DB-free tests).

## Per AC (one evidence block each: pass / fail / partial / live check pending)
- AC-1 strikes around ATM for the underlying and expiry, width 10/20/30/40 (default 10), ATM marked; a NIFTY and a SENSEX
  expiry from the recording.
- AC-2 CE/PE LTP and OI per strike from the platform's feed; IV and delta from the engine - recompute two strikes by hand
  (Black-Scholes with the engine's inputs) and compare.
- AC-5 without live data: strikes still listed (centre LIVE_SPOT / LAST_KNOWN_SPOT / MIDDLE_STRIKE), every price null with
  the reason; a stale quote never returned as current.
- AC-6 every listed futures expiry with its LTP (futures tick from the feed; NO_QUOTE / FEED_STALE / NOT_STREAMABLE
  reasons) and per option expiry the forward used for pricing (parity or labelled spot fallback). The futures LTP was
  proven only on a real packet re-addressed to a synthetic future (no recording holds a futures tick): judge whether
  that is `live check pending` or a fail.
- AC-7 depth: 5 levels of bid and ask with quantities, day open/high/low (previous close where the packet carries it),
  last trade time, time read; no order route anywhere in the module.
- AC-8 depth not readable (no session, stale feed, not streaming, empty or zero levels): `not available` with the reason,
  never an empty or old table; day stats unavailable carries its own reason.

Also judge: (a) the `# noqa: PLR0915` added on `create_app` in `backend/ofo_app/main.py` - acceptable precedent or a ratchet
dodge (say which, with the ratchet rule); (b) the strikes/futures leases (30 s release after the last read, a second lease
on the shared fan-out - no second socket): read twice, then stop reading, and show the subscription count returns to its
start.
Mutation (Tier A): on scratch copies - return a stale price as current; drop the zero-level filter; serve day stats as
null instead of the reason; compute IV outside the engine - each must be killed; quote which test.

Threat model: in scope - a stale or invented price, an empty/old depth table, a value computed outside the engine, a
silent null, a guard or ratchet loosened, a leaked subscription; out of scope - the frontend picker and popup (row 19
frontend part), order placement (none exists).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory, domain-test-imports-app-package

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - per AC: verdict, route, exercised there yes/no, command, output line; then numbered findings
CRITICAL / MAJOR / MINOR with file:line. Under 500 words.
