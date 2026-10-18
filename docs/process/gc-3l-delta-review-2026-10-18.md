# Review of the GC-3L delta + runbook (chain rule 3; fresh Opus, 2026-10-18)

Files: `goal-contract-GC-3L-delta-2026-10-18.md`, `gc-3l-runbook-2026-10-19.md`, F-44 in `spec/findings.md`.
Round 1 verdict: **CHANGES NEEDED**, 0 CRITICAL, 2 MAJOR, 6 MINOR. No step touches ofo_test, places an API order, or
has Claude click on Kite's page. Every Monday command exists on main with the arguments given (wiring map below).

| # | Sev | Finding | Decision |
|---|---|---|---|
| 1 | MAJOR | EXIT stalls: the Prepare buttons show only while the page holds no reply (`ExecuteStrategyPage.vue:104`) | Accepted (checked: `v-if="!reply && ..."`): reload the tab after Check, never before |
| 2 | MAJOR | ADR-108 rule 5 (net 0 on the contract) has no step; `probe.py` has no positions command | Accepted: 09:20 owner check on Kite's Positions/Orders + screenshot |
| 3 | MINOR | The F-41 return query cannot be read from the address bar (the forward drops it; private window keeps no history) | Accepted (checked `routes/broker.py:11,70`): Network panel with "Preserve log", keys only |
| 4 | MINOR | No fallback for a failed freeze download / catalogue reload; reloads must finish before the API starts | Accepted |
| 5 | MINOR | Rs 5-11 cited to ADR-108 (2); it is the owner's 2026-10-18 decision | Accepted |
| 6 | MINOR | L4 `--tag-prefix` not given; tags are `OFS{s}V{v}L{i}` | Accepted (checked `basket.py:94`): `OFS<id>V` |
| 7 | MINOR | The screen shows no product column, so NRML is confirmed on Kite's page | Accepted |
| 8 | MINOR | `monday-before.json` would land in the repo root with account data | Accepted: absolute path under `ofo-kite-ticks/2026-10-19/` |

Wiring map (reviewer, from main): step 0.1 -> newest product-code commit 04500d4 (#383), its App tests run green with
`execute-screen-e2e`; catalogue -> `ofo_app.catalogue_load`; freeze -> `scripts/load_freeze_file.py` ->
`freeze_store.run`; API -> `ofo_app.main:create_app` + `event_loop.selector_loop`; login -> `/broker/zerodha/login` ->
`live_market.pick_up_login`; probe -> `probe.py holdings|contract|pnl|audit`; screen -> `SaveDraftBar.vue`,
`StrategyActions.vue`, `ExecuteStrategyPage.vue`, `BasketForm.vue`, `ReturnCheck.vue`, `ExecutionReturnedPage.vue`;
EXIT quantity -> `execute_plan.held_units` / `exit_legs`.

Round 2 (re-check of the eight fixes only): see the section below.

## Round 2
Fresh Sonnet re-check of the eight fixes: all 8 FIXED (path:line each); the reload-before-EXIT step cannot lose the
ENTRY Check (step 7's two Checks come before step 8's reload; the no-fill and partial branches never reload); no
contradiction with GC-3L times or amounts. One new MINOR: the runbook called Rs 11 "within" ADR-108 (2)'s "about Rs 650
or less" though Rs 11 x 65 = Rs 715 - accepted: runbook and delta now say prefer a premium of Rs 10 or less.
**Verdict after round 2: READY** (no CRITICAL or MAJOR open). Review rounds used: 2 of 2.
