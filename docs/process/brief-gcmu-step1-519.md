# Brief: GC-MU step 1 (core) - #519 / REQ-050: shared-compute keys built from the engine call

Core: one option's figures computed once per price update and read by every strategy, with a cache key that cannot drift from what the engine reads (REQ-050 AC-1/AC-3, issue #519).
Proof: step 1 of this brief - 1,000 strategies on the same NIFTY strike fed the recorded ticks: engine call count = 1 per update; then the 40-mutant key script: 0 non-redundant survivors.
Budget: 60 min wall-clock, 120 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: F-59, F-77 (spec/findings.md); knowledge/findings grep for shared_compute and cache key
Spec quote: REQ-050 AC-3 "No identical market metric is computed separately per user."
Threat model: must stop a later edit that drops or changes one input of an engine call while the cache key keeps the old parts (stale figures served to every reader with every test green). Need not stop deliberate misuse of `SharedCompute.get_or_compute` with a hand-built `SharedKey` outside the helper (write that bypass in the module docstring).
Sensibull: n/a - backend cache, no screen.
Reference: none - searched shared computation, cache key, Greeks once per update (backend only, no screen in the study)
Copy from: not used this round - the shared-compute cache was already built in chunk 1 (#525); the REQ-050 map rows `ticker/pool.py` (414), `market_data/rate_limiter.py` (135), `services/options/option_chain_live_engine.py` (222), `services/options/option_chain_cache.py` (145), `services/options/option_chain_prefetch.py` (149) cover the feed/chain layers, not the key helper this brief changes.
Tier: A (fresh Opus verifier follows; mutation tests required).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-gcmu-key`, branch `build/gcmu-key` (from `build/gcmu`). Commit there only. Never push. Never touch `main`, `feature/adjustments`, `build/settings` or any `build/gcset-*` tree.

## Read first
- Issue #519 (gh issue view 519 -R abhayla/OptionsForOptions2): what stays and what is left.
- `backend/ofo/marketdata/shared_compute.py` (the cache), call sites `backend/ofo/outcome/service.py` (~lines 500-560: `leg_iv` and `leg_greeks`) and `backend/ofo/outcome/snapshot.py` (~line 80: parity forward).
- The old mutant driver (read it, copy it into your worktree scratch, do not edit the original): `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\b9b5cb32-ea0c-400f-80e1-fbd7045cbf2a\scratchpad\verify-08r2\mutate.py` and its result `mutate2.log` (30 of 40 survived).
- Tests: `tests/marketdata/test_shared_compute.py`, `tests/marketdata/test_shared_compute_concurrency.py`, `tests/outcome/test_snapshot_instant.py`, `tests/outcome/test_input_states.py`, `tests/marketdata/test_scale_classes.py`.

## Do, in order
1. CORE PROOF FIRST (before any refactor): a test `tests/marketdata/test_shared_compute_scale.py` that builds 1,000 strategies holding the same NIFTY strike (use the recorded snapshot / scenario fixtures already used by the tests above; no captured Kite quotes added to the repo), feeds a sequence of at least 3 price updates, and asserts the engine functions (IV solve, leg Greeks, parity forward) each run exactly once per update per contract (count via `SharedCompute.computations` and/or a counting wrapper on the engine function). Run it and record the counts. If it fails, STOP and report: that is a core failure.
2. Structural fix (#519 item 1): one helper in `shared_compute.py` (e.g. `FeedScope.call(scope, fn, *args, **kwargs)`) that builds the `inputs` part of the key FROM the exact arguments it passes to `fn` and then calls `fn(*args, **kwargs)` itself. Every argument must be hashable or reduced by ONE documented normaliser (dataclass -> tuple of its fields via `dataclasses.astuple`/fields walk, Decimal kept exact, datetime kept). An argument the normaliser cannot reduce raises (fail closed), never silently drops out of the key. Move the three call sites onto it so the hand-written `inputs = (...)` tuples are deleted. The function identity (module + qualname) is part of the key, so the `figure` name can no longer point two different functions at one entry.
3. Second layer (#519 item 2): one parametrized test on the recorded snapshot that changes ONE input at a time at the same instant (every field each engine function reads: kind, strike, price, spot level, forward, implied yield, years, rate, days in year, dividend yield, leg iv, each quote's bid/ask/timestamp/health, spot ltp/timestamp/health, expiry) and asserts the figure is recomputed AND equals an unshared direct call.
4. Re-run the mutant script, adapted to the new code: every way to drop one argument from what reaches the key while the engine still reads it. Report: total mutants, killed, survivors, and for each survivor why it is redundant (e.g. `strike` duplicates `instrument_id`). Target: 0 non-redundant survivors. Also the 5 Tier A guard mutants (normaliser drops a field; helper calls fn with an argument not in the key; function identity left out; feed owner left out; exception cached) - each must turn a test red.
5. Guard tests: `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`. Run in full every test file you changed plus the 5 listed above, output to a log file, read the tail. `python -m ruff check` on changed files; ruff/mypy baselines must not rise (`python scripts/ruff_ratchet.py`).

## Standing items
- One test per acceptance criterion; targeted test files only, output to a log file, tail only; a skipped test counts as not run.
- Every test file you changed is run in full, not a name-filtered subset.
- Answer states for the normaliser: hashable value (kept), dataclass (reduced), None (kept as None), unhashable/unknown type (raise), empty tuple (kept). Each has a test.
- No shown value changes (backend cache only); still grep `tests*` for any number you change.
- Tier A: the mutation test above; at most 5 guard mutants on a scratch copy (`scripts/orchestrator/mutation_gate.py` if it fits).
- Known bypasses written in the module docstring, not chased.
- Money and figures stay exact Decimal (ADR-008); no float introduced.
- No new duplicated literal; reuse the existing helper; targeted tests only; no regenerated files in the commit.
- Commit after each item passes (so a restart loses at most one). Do not edit `backend/ofo_app/routes/outcome.py` (shared with another session); if a change there is unavoidable, stop and report it instead.
