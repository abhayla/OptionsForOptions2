# Row 8 fix round 2: REQ-050 shared computation (W-136) - every route shares, Greeks shared, two discriminating tests

Common brief: docs/process/builder-brief.md (Budget hard stop: at 64 calls start nothing new, leave the tree
consistent, commit, report; scratch-copy mutations; fix lint as you go; R13).
Size: M, 9 files, 5 items
CI: kit tests job (`tests/marketdata/test_shared_compute.py`, `tests/outcome/*`, `tests/table/*`; vars: none); app job
`api` step (`tests_app/test_strategy_planned_entry.py`, `tests_app/test_planned_entry_holds.py`, `tests_app/test_strategy_tracking.py`, `tests_app/test_db_pool_core_proof.py`,
`tests_app/test_strategy_shape_matrix.py`, `tests_app/test_strategy_store.py` and every file item 5 selects; vars:
TEST_DATABASE_URL only) - run them through
`python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`
(NOT db_run.py: the worktree has no .env; the launcher uses the main checkout's).
Expected (orchestrator, before dispatch 2026-10-22): build 60 min / ~150k tokens; verify round 2 20 min / ~170k.

Core: two readers of one live snapshot share every market-wide figure (each leg's IV and per-unit Greeks, each
expiry's forward) on EVERY route that reads a snapshot: the second reader computes nothing.
Proof: step 1 is a failing test on the recorded frames (`tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`)
through the REAL outcome path: two readers of one snapshot -> the second reader's per-unit Greek computations are 0
(at 85de202e they are not: `table/model.py:252` computes them per strategy).

Spec basis: REQ-050 AC-1: "Shared once for all users: normalization, shared Greeks, underlying state, option-chain
metrics, contract metadata, market-wide derived metrics." REQ-050 AC-3: "No identical market metric is computed
separately per user." ADR-053 (V1: per user's own feed, so the feed owner stays in every key).
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head e79086cf. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\row08-fix2`.

## What to do (verify round 1 findings; orchestrator decisions, technical)
1. Every snapshot reader shares: pass `FeedScope(SHARED_COMPUTE, ctx.feed_owner)` (None when there is no feed owner,
   exactly as `ofo_app/routes/outcome.py:442`) into `read_snapshot` at `ofo_app/routes/planned_entry.py:79` and
   `ofo_app/routes/tracking.py:120`, and into the outcome build on those routes if they build one. Add a test per route
   that two requests on one snapshot run the forward computation once (counter `SHARED_COMPUTE.computations`).
2. Make `test_100_concurrent_first_requests_for_one_key_run_one_computation` discriminate: the compute blocks on a
   `threading.Event` that is set only after all 100 threads have started; assert exactly 1 computation. Prove it in a
   scratch copy with the per-key lock removed -> the test goes red (the round-1 verifier's probe
   `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-08\coalesce_probe.py`
   shows the shape: 100 calls without the lock, 1 with it).
3. Shared per-unit Greeks (orchestrator decision: BUILD, do not narrow - AC-1 names "shared Greeks", so narrowing
   would be a spec change). Compute each option leg's per-unit unrounded Greeks once per key through the same
   `FeedScope.compute` the IV uses (`outcome/service.py:396-397`), figure `"leg_greeks"`, the inputs being exactly
   what `leg_greeks_unrounded` reads (iv, spot/forward, strike, kind, rate, instant, expiry yield). Hand them to the
   table model as an input (allow-list: the table model takes a per-leg per-unit Greeks value the caller supplies, else
   computes it itself as today; it never caches). The engine (`ofo.engine.model.leg_greeks_unrounded`) stays the one
   home of the maths. Rounding and position scaling stay in `table/model.py`, unchanged. Test: two readers -> second
   reader's Greek computations 0, and its Greeks equal an unshared read exactly (Decimal equality).
4. A test where only the spot changes at the same instant (same chain quotes) and the forward recomputes (kills
   mutation M15: forward key without the spot). Re-run M15 in a scratch copy and report it red.
5. The 3 app files that failed in round 1 on a dropped DB tunnel (`tests_app/test_db_pool_core_proof.py`,
   `tests_app/test_strategy_shape_matrix.py`, `tests_app/test_strategy_store.py`) and R13's selection for YOUR
   commits (every `tests_app` file importing planned_entry, tracking, outcome service, table model, snapshot) run
   green through the launcher; list each file and its result line.

Attack list: (each names its test file)
1. Two readers one second apart on one recorded snapshot -> 0 new IV, Greek and forward computations for the second
   (`tests/marketdata/test_shared_compute.py`, through the real outcome path).
2. Shared Greeks equal an unshared read exactly; a leg with no IV has no Greeks and caches nothing; a futures leg is
   untouched (`tests/outcome/` or `tests/table/`).
3. Planned-entry and tracking routes share the forward with the outcome route on one snapshot
   (`tests_app/test_strategy_planned_entry.py`, `tests_app/test_planned_entry_holds.py`, `tests_app/test_strategy_tracking.py`).
4. 100 concurrent first requests -> exactly 1 computation; red without the per-key lock
   (`tests/marketdata/test_shared_compute.py`).
5. Spot-only change at one instant recomputes the forward; two users' feeds never share Greeks
   (`tests/marketdata/test_shared_compute.py`).
6. The guard tests and the item-5 files pass (commands above).

Standing items: (a) n/a: no time-budgeted job in this change; (b) n/a: no CI step changes; (c) n/a: no static detector added; (d) n/a: decides on no other system's answer (the cached figure is our own engine's).
Threat model: in scope - a reader served another feed's or another snapshot's Greeks, a route that bypasses the shared cache; out of scope - a licensed shared vendor feed.
Findings checked: caller-supplied-verdict-trusted, dependent-tests-not-run-stale-later, wall-clock-assertion-flakes-under-load
Reviewer checklist: real outcome path in the core test; Greeks maths only in the engine; table model never caches;
each route's test fails if its FeedScope is removed (scratch mutation); M15 and the no-lock mutation re-run red; every
item-5 file listed with its result; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not
rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Legacy map rows (copy_from_check.py)
Rows of the legacy-reuse map that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read
before designing; SKIP -> do not re-survey.

| `market_data/rate_limiter.py` (135) | COPY | set Kite limits (legacy had 3 req/s; Kite docs say 10, verify at P3a) | REQ-050 |
| `services/options/option_chain_live_engine.py` (222) | ADAPT | strip platform-wide assumptions | REQ-029, REQ-050 |
| `services/options/option_chain_cache.py` (145) | ADAPT | row 5; no cross-user sharing until ADR-034 | REQ-050 |
| `services/options/option_chain_prefetch.py` (149), `startup_chain_warmup.py` (270), `option_chain_service.py` (458) | REFERENCE | built on the platform adapter / duplicates | REQ-050 |
