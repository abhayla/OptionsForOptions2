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

Answer: (pending)
