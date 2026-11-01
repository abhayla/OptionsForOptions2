# Owner questions, 2026-11-01 (GC-SET run, written while the night guard blocks question boxes)

## Q-GCSET-1 (06:51 IST): restart the integration gate that the PC killed for low memory?

What happened: the integration gate for batch 2 (worktree `OptionsForOptions2-OptionsForOptions2-gcset-int2`, branch
`build/gcset-int2`, head 85fd0fa8 = steps 4c, 4e, 5a, 5a-2 and 8) was killed by Claude Code at ~06:45 because the PC
ran critically low on memory (the GC-MU session runs its own builders at the same time). Claude Code's rule: a job it
killed for memory is restarted only when the owner asks.

Already green on 85fd0fa8: full pure `tests` 8640 passed / 0 failed; both openapi drift checks; DB files
adjustment_approaches_route 64, adjustment_check 8, adjustment_opportunities 12.
Not finished: 9 DB files (user_preferences, scenario_mode, settings_route, settings_speeds_wiring, paper_settlement,
chain_live, leg_edit_route, outcome_route, order_closure_all_routes) and the full vitest run.

Spec basis: none - the spec says nothing about test scheduling (searched: memory, gate, vitest); contract §0.1 says DB
tests run one file per run and heavy jobs need enough free memory.

Options:
1. **Restart, one at a time (recommended)**: the 9 DB files strictly one after another, then vitest alone on the
   heavy slot, no builders in parallel. Lowest memory use, about 25 minutes. If green, build/settings fast-forwards to
   the batch and the run continues (market hours, 5b, step 6 guard, step 8 UI, step 9, browser proofs, close).
2. Wait for GC-MU to report no builders running, then restart.
3. Do not restart; build/settings stays at 4c029a29 (steps 1-3, 3b, 4a, 4b, 7, all gated).

Answer (owner, 2026-11-01 ~07:50 IST, chat): "Restart the gate" -> option 1, one file at a time.

## Q-GCSET-2 (09:13 IST): how should the PC be shared between GC-SET and GC-MU heavy jobs?

The memory reaper killed GC-SET's runs and waits 4 times since 06:45 and GC-MU's prepush once.
Answer (owner, 2026-11-01 ~09:15 IST, question tool): "GC-MU finishes, then GC-SET" - wait for GC-MU's heavy slot,
then run the remaining gate runs in the foreground in short chunks.

## Q-GCSET-3 (13:07 IST, information + one decision): why the VPS DB runs were slow

Owner asked (~12:45): check why the VPS is slow and fix what we cause. Read-only findings (Windows VPS 103.118.16.189):
- CPU 1% at the check, one active DB connection: nothing stuck now. The slow DB test runs (1-11 min a file) came
  mainly from our own load: every `db_run_fresh` run creates a fresh database and runs all 34 migrations, and GC-MU
  and GC-SET ran such files at the same time; GC-MU is done now.
- FIXED: 39 leftover throwaway test databases `ofo_test_tmp_*` (0.43 GB, some from 2026-10-23, left when a run's drop
  step failed, e.g. on a tunnel drop) dropped with the tool's own `db_run_fresh.py --sweep` (older than 24 h only).
- MY MISTAKE, fixed: a recursive disk-size scan I started ran ~8 min on the production box (PID 14808); killed by
  PID. No further scans.
- NOT mine, owner's decision: disk C: is 88% used (13 GB free of 110), over the 80% rule; the databases are ~1.2 GB of
  it. Recommendation: run (or check the last run of) the weekly VPS disk-hygiene job for that box (old releases,
  journals, caches); I have not deleted anything on it.
- Not a cause: the `claude.exe` process on the VPS has run since 2026-10-09 with ~4.5 CPU-hours in total.
Answer: (pending)

## Q-GCSET-4 (17:2x IST, written while the owner is away): should a rate change visibly move the builder's Greeks?

SPEC CHANGE question. The goal prompt (item 3) said: if the builder's Greeks do not move at the stored rate 0.07, treat
it as a defect, fix the class and add a test. Measured (F-82): they move only at the third decimal (per-unit Theta
15.988 -> 15.987; IV 13.10% at both rates), because the engine reads the forward from put-call parity, so a higher rate
is absorbed by a higher implied dividend yield (q for 9 Nov -0.0000115 -> 0.0050063). The rate does reach the builder:
`tests_app/test_scenario_rate_wiring.py` core test passes ("figures changed by the rate: dividend_yields, legs, table").
Making the Greeks visibly move needs q held fixed, which changes the pricing model.

Spec basis: ADR-220 ("pricing model kept"); ADR-061 and ADR-063 (forward from parity; the engine owns q); REQ-167 AC-1
(the registry's "what it changes" line for `pricing.risk_free_rate`).

Options:
1. **Keep the model; reword the Settings line (recommended).** Say the rate sets the forward and, on a liquid chain,
   mostly shifts the implied dividend yield, so prices and Greeks move very little. No pricing change, no risk.
2. Keep the model and the current wording (the line over-states the visible effect).
3. SPEC CHANGE: change the pricing model so the rate moves IV and Greeks directly (reverses ADR-220's "pricing model
   kept"; Tier A; its own contract).

Answer (owner, 2026-11-01, question box): "(a) Fix the text only (Recommended)"; then "assume a role of expert option
trader ... take a decision ... proceed with your recommendation". Recorded as ADR-222 (12); registry line reworded.
