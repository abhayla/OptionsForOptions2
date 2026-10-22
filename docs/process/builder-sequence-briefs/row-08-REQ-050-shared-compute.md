# Row 8: REQ-050 Shared computation (W-136, builder sequence chunk 1, Tier A)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; every changed test file in
full with its CI job's variables; fix lint as you go, no bulk noqa). Expected (row-review, set 17:20 IST before
dispatch): ~90 min / ~450k tokens (measure 6 + build 60 + verify 20 + orchestrator 10).
Size: M, 8 files, 4 items
CI: kit tests job (`tests/marketdata/test_shared_compute*.py`, `tests/marketdata/test_scale_classes.py`; vars: none);
app job `api` step only if a route test is added (vars: TEST_DATABASE_URL only).

Core: a market-wide figure (a chain snapshot's IVs and Greeks) is computed once per feed snapshot and served to every
screen and strategy reading that feed, never recomputed per reader, and never across two users' feeds in V1.
Proof: step 1 is a failing test replaying the recorded frames (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`)
into two readers of the same feed snapshot with a compute counter: today each reader computes (counter 2); after the
build, 1.

Spec basis: REQ-050 AC-1: "Shared once for all users: normalization, shared Greeks, underlying state, option-chain
metrics, contract metadata, market-wide derived metrics." REQ-050 AC-3: "No identical market metric is computed
separately per user." ADR-053 (V1 reading of both): "calculations that are identical for everyone run once per market
snapshot but only on data that user is entitled to see" - so V1 shares within one user's feed, and across users only
once a licensed vendor exists (F-23: one user's feed cannot drive another user's screen). The load-test criterion
(AC-4) is DEFERRED by ADR-053:
"The 5k-500k scale saving of ADR-012 waits for a vendor licence (REQ-052 AC-5)". AC-2 (per-strategy work stays per strategy) is re-verified, not changed.
Copy from: legacy-reuse map rows for REQ-050, appended below by copy_from_check.py (act on each; legacy-reuse.md says
no cross-user sharing until ADR-034 is answered).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row08`.

## Measured starting state (2026-10-22, branch head)
No code computes or caches IVs, Greeks or chain metrics once: `chain_push.py:7` drops IV and Greeks; `forward.py`
derives the forward per call; `fanout.py` shares vendor subscriptions only (`tests/marketdata/test_fanout_replay.py`).
Per-strategy computation lives in `ofo/table/model.py`, `ofo/engine/*`, `ofo/rules/*`.

## What to build (orchestrator decisions, technical)
1. `backend/ofo/marketdata/shared_compute.py`: a cache of market-wide results keyed by an allow-list key
   (feed owner, underlying, expiry, snapshot instant) - the feed owner is part of the key in V1, so two users' feeds
   never share an entry; one computation per key with concurrent first requests coalesced; a failing computation is
   not cached and does not affect other keys; bounded memory (entries for older snapshots evicted).
2. Use it for the chain snapshot's per-contract IV and Greeks (through the one engine, ADR-008) and the forward, in the
   one place the outcome / chain code computes them today; screens and strategies of the same feed read the shared
   result.
3. A test-only class table (`tests/marketdata/test_scale_classes.py`): the modules that compute per-strategy results
   (P&L, risk, rules) never read from or write to the shared cache (an allow-list of which modules may import it).
4. One line in the requirement's place for AC-4: nothing to build (deferred by ADR-053); the evidence says so.

Attack list: (each names its test file)
1. Two readers of one feed snapshot -> compute counter 1 (`tests/marketdata/test_shared_compute.py`).
2. A new snapshot instant -> a new computation; the old entry is evicted (same file).
3. Two users' feeds with identical data -> two computations, no shared entry (ADR-053 / F-23) (same file).
4. 100 concurrent first requests for one key -> one computation (`tests/marketdata/test_shared_compute_concurrency.py`).
5. A computation that raises -> not cached, the next request computes again, other keys unaffected (same file).
6. A per-strategy module importing the shared cache -> red (`tests/marketdata/test_scale_classes.py`).
7. The shared IVs/Greeks equal the engine's per-contract result on the recorded frames to the last digit
   (`tests/marketdata/test_shared_compute.py`).

Standing items: (a) the computation runs inside request/push paths: a test shows a slow computation for one key does
not block reads of other keys; (b) n/a: no CI step changes; (c) the class-table import check is an allow-list,
discovers modules and fails closed on one it cannot parse; (d) n/a: the feed's answers are already classified by
REQ-049 (a non-AVAILABLE quote keeps its health through the shared result).
Threat model: in scope - one user's feed serving another user's screen, a per-reader recomputation, a poisoned shared entry; out of scope - a licensed shared vendor feed (not built).
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted
R13: for every backend file you change (outcome/chain code especially), grep the `tests_app` files that import it or
call its routes and run them all through the throwaway-database runner; list them in the report.
Reviewer checklist: recorded frames for the equality test; the feed owner in every key; coalescing proven with a
counter, not timing; eviction bounded; the class table an allow-list; every guard has a test that dies without it
(scratch-copy mutation list); every changed test file in full with CI's variables; no new duplicated literal; reuse the
existing helper; ruff baseline must not rise; targeted tests only; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `ticker/pool.py` (414) | ADAPT | row 1; drop `can_auto_refresh`/`refresh_broker_token` (`:23-24`) and platform credentials | REQ-048, REQ-050 |
| `market_data/rate_limiter.py` (135) | COPY | set Kite limits (legacy had 3 req/s; Kite docs say 10, verify at P3a) | REQ-050 |
| `services/options/option_chain_live_engine.py` (222) | ADAPT | strip platform-wide assumptions | REQ-029, REQ-050 |
| `services/options/option_chain_cache.py` (145) | ADAPT | row 5; no cross-user sharing until ADR-034 | REQ-050 |
| `services/options/option_chain_prefetch.py` (149), `startup_chain_warmup.py` (270), `option_chain_service.py` (458) | REFERENCE | built on the platform adapter / duplicates | REQ-050 |
