# Session handover - GC-MU integration into feature/adjustments, 2026-11-01

Goal (owner choice 2026-11-01: "GC-MU integration only"): merge `build/gcmu` (acf66307) with `feature/adjustments`
(c5371647, GC-SET) into one tree, swap the two MERGE-SWAPs, run `prepush.py --full` once on the final merge head and
push `feature/adjustments` fast-forward. Never main, never a PR. Run tree `D:\Abhay\Ventures\OptionsForOptions2-gcmu`.

The gate result for the final head is recorded in `OptionsForOptions2-coord/log.md` and the memory note
`gcmu-integration-2026-11-01.md`, not here: this file is committed before the gate runs (the pass marker needs a
clean tree from start to end).

## DONE

- **Merge** of origin/feature/adjustments into build/gcmu: 18 conflicted files resolved with the GC-MU overlap ledger
  (GC-SET kept no separate ledger; its contract's step log stands in). GC-SET's settings values win where they differ.
  - `compare.py`: `Context` keeps both new fields (`view` first, since `limits` has a default); `cost()` is GC-SET's
    `approach_cost` (ADR-221) with GC-MU's charge breakdown attached.
  - `outcome/snapshot.py`: GC-MU's `call_shared` keying (every argument) plus GC-SET's forward `quality`.
  - `routes/adjustment.py`: `priced_approach` gains keyword-only `limits` / `max_profit` (default None, so T-19's
    callers are unchanged); the route passes GC-MU's guards through GC-SET's one build path.
  - Template pins: three-way JSON union, 806 base + 23 GC-MU + 31 GC-SET = 860, owner-review stamps kept.
  - Order-closure pin: 31 + 2 (GC-MU A1) + 2 (GC-SET step 9) = 35, confirmed by the test.
  - Migrations: no GC-MU migration past 0034, so nothing to re-point (one head, 0034).
- **MERGE-SWAP 1 (speeds):** five registry keys added WITH their reader (`speeds.per_option_seconds`,
  `speeds.background_check_seconds`, `speeds.valve_step_seconds.1/.2/.3`; defaults 1/1/1/2/5 as before).
  `calc_speeds.py` reads the settings mapping the caller read; `_STAND_IN` is gone and listed as an old home in the
  literal guard. The valve's load limits (0.5 s, backlog 50, calm 30 s) stay in code: not user-visible figures.
- **MERGE-SWAP 2 (cost):** `compare.cost_pct()` reads the cost cell, which is now ADR-221's `approach_cost`.
- **Hidden breaks found by type-checking every GC-MU file** (the text merged cleanly, the code did not run): the
  background role imported `LIVE_RATE` (deleted by GC-SET) and called `parity_forward` without `quality`,
  `resolve_spot` without `windows`, `state_of` without `config` and `evaluate_and_remember` without `gap_until`. Fix:
  the background `Worker` takes `settings` (one read per cycle: speeds, valve steps, rate, forward settings, feed
  windows) and `preferences(user_ref)` (each owner's REQ-168 preferences). A failed settings read keeps the last good
  one; with none yet, nothing is checked.
- **T-19 background vs screen** (found by the field-by-field core test, red 3 vs 6 unpriced): the background built its
  chain rows from the held legs only, the screen from every listed contract, so T-19 saw different strikes. Fix
  (structural): one `adjustment_readers.chain_rows` + `listed_options` used by both; only the Greeks source differs.
  Cost: `test_background_cycle.py` 11 s -> 27 s (per-option figures for the whole expiry chain, shared per price
  update).
- **Expiry kind in the background** (found by the DB core test: `KeyError: ''` in `roll_distance`, so no record opened):
  `Watched.expiry_kind` was never set by the lister, so the background fell back to the stored position's `''`; GC-SET's
  T-19 now builds a roll in the background and the roll reads the target delta by expiry kind. The test fixtures hid it
  by passing `"weekly"` by hand. Fix (structural): one `adjustment_readers.expiry_kind_of` (screen and background), the
  futures expiries cached with the listed options; the field and the hand-set fixture value are gone.
- **The 1 s core proof over the tunnel** (step 4, `test_background_worker`): passes at gap 0.990 s (was 0.40-0.61 s
  before the merge). Measured: the check's own computation 0.083 s; the crossing record is 7 SQL statements on a pooled
  connection; tunnel query round trips 0.06-0.15 s, a fresh connection 0.45 s (20:15 IST). GC-SET's diff adds at most one
  read to this path (`playbook_store._current`). So the margin is network, not code: on the production host the same 7
  statements take milliseconds. The bound is kept; the test may fail on a slow tunnel and is reported with these numbers
  if it does.
- **Template codes:** GC-MU's roll refusals moved 173/174 -> 176/177 (GC-SET's T-19 reasons keep 173/174).
- **Guard widened:** `tests/test_settings_reader_guard.py` also accepts `feed_windows(<values name>)` (the background
  has no request context); `feed_windows(defaults())` and attribute shapes stay refused, with tests both ways.
- **Generated:** findings index, spec digest, build order, requirements index, scenario fixtures (only ADJ-50 changed
  in content: T-19 cost 329.00 -> 73.24 via A-29, from GC-SET's generator), reply inventory (21 GC-SET reply owners
  reviewed, 0 UNREVIEWED), OpenAPI (no change beyond the merge).
- **Checks before the gate:** collect-only over tests_app 5325 tests, 0 errors; non-DB overlap set 2920 passed;
  non-DB overlap app files 445 passed, 1 skipped; DB overlap files (fresh DB each): adjustment_opportunities 14, adjustment_check 8, adjustment_plan 7, background_worker 2 passed.

- **Gate run 1 on f04783b8 (20:25-21:00, 2109 s): red on 2 steps, neither a code defect of the merge.**
  - `domain_tests`, 1 of 8830: the bundle secret scan read a STALE `frontend/dist` (built 17:57 by GC-SET's gate with
    GC-SET's Vite config, no manifest); GC-MU's scan (#517) allows the Kite basket `api_key` only through the manifest
    and fails closed without one. prepush runs the domain tests BEFORE its own frontend build. On the fresh build (21:00,
    with `.vite/manifest.json`) the same file: 70 passed. Fix for the rerun: build first.
  - `frontend_unit`, 2 of 1850 (`option-chain.test.js` row 33, attack 6): failed once under the full parallel run, passed
    in 7 reruns (alone, under CPU load, full suite). Not reproduced, so the root cause is unproven; the shared
    `mountPage` now waits (bounded) for the settings answer the strike options come from.
  - Mechanism for both classes: `scripts/orchestrator/merge_preflight.py` (branch build/merge-preflight, owner ask
    2026-11-01 evening), checked in BEFORE the long gate.

## PENDING
- Close: merge `--no-ff` build/gcmu into local feature/adjustments, `prepush.py --full` on that head (heavy slot),
  push fast-forward. Result: coord log + memory note.

## DEFERRED
- #633: T-19 (`adjustment_check.cheapest_offered`) builds approaches without the playbook's liquidity limits the
  Compare now applies. Unmeasured whether any scenario hits it (candidate ADJ-50).

## Lessons
- **A clean textual merge is not a working merge.** Five call sites in a file with no conflict were broken by the
  other branch's signature changes. A type-check (mypy, call-arg / attr-defined only) over every file one side touched
  found all five in one run; the tests would have found them one at a time.
- **A field-by-field equality test between two paths is what caught the T-19 split.** Keep such core tests whenever
  two roles must answer the same question.

## NEXT
1. T3 at the first market session with the owner present (Mon 2026-11-03 09:15 IST earliest).
2. #633 (T-19 limits), #628 (seeded ADJ-13 batching) before further screen proofs on those scenarios.
3. #629 wording check of the pending texts (the texts are final after this integration).
4. GC-SET2 (#632) when the owner sets it. Nothing to main without the owner's explicit OK.
