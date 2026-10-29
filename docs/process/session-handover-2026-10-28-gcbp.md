# Session handover: GC-BP (builder -> paper trade -> Positions Paper tab), 2026-10-28

Contract: `docs/process/goal-contract-GC-BP-2026-10-28.md` (its walk 1, walk 2, F-rows and visual tables hold the
evidence). Branch `build/gcbm-must-have` in `D:\Abhay\Ventures\OptionsForOptions2-gcbm`, LOCAL ONLY: no upstream, no push,
no PR, no CI in this goal (owner, commit aa1f626c). GC-BM's 86 commits + GC-BP sit together on this branch for one later
land goal.

## DONE

- Step 0: overlap list (no GC-BM commit touched tracking or positions; reuse points named).
- Step 1 core proof: build -> Save -> Start tracking -> paper P&L read twice, server moving; the screen did not move ->
  F-1 fixed (panel re-reads every 5 s), proven live (-104.00 -> -84.50).
- Steps 2 and 7: walk 1 (P-1..P-8 = strategies 46-53) and walk 2 on the final code (Paper tab, exits by the screen,
  PX-1..PX-4, P-list rebuilt = strategies 54-61). Walk 2 clean: no new F-rows.
- Step 3: F-1 (paper panel froze), F-2 (strike drawer dropped picks on an expiry change), F-3 (real Positions page never
  loaded: 145 DB queries ~12 s vs the browser's 10 s; now 5 queries, 1.3 s). Each re-tested live.
- Step 4: `GET /tracking` (every paper strategy of the user, total / booked / unbooked, fixed query count, one market
  read per index). Step 5: `POST /strategies/{id}/tracking/exit` (partial or full, append-only, migration 0027, refused
  when a leg is not live, a leg exits once). Tier A mutants 5 of 5 killed.
- Step 6: Positions page tabs "Positions" / "Paper"; one shared Paper list (also in the builder's Tracked tab); one
  refresh composable for every paper figure.
- ofo_dev migrated 0026 -> 0027 (owner role, 11:15 IST).
- Step 8 review, 2 rounds: Opus Tier A backend PASS (4 MINOR fixed: pause on price STATE not price presence; an exit of a
  not-live contract gets its own refusal 436 instead of "try again"; migration 0027, batch-equivalence and exit-race tests);
  Sonnet frontend REVISE -> F-4 (builder ignored in-page ?strategy= links) fixed and re-walked live; round 2 PASS.
- Frontend vitest after the last merge: 78 files, 1270 passed. API restarted on the final code (PID 11976).

## Gap-list re-verdicts (docs/process/builder-gap-list-2026-10-27.md)

| Gap | Was | Now |
|---|---|---|
| G-029 (builder Positions tab, S-119) | unmeasured | differs: "Coming soon: Positions" (read 11:4x IST); not in GC-BP scope (later goals B16/B17) |
| G-030 (Draft Portfolios / Tracked tab, S-118) | differs: "No tracked strategies here" | partly matches: the Tracked tab and the new Positions Paper tab list every paper strategy with legs, entry, LTP, exit, total / booked / unbooked and exit actions (Sensibull 090-092 content); no named portfolios / "Create New Portfolio" (Sensibull groups drafts into portfolios) |
| G-075 (drawer cells, S-032) | matches (GC-BM) | structure still one value per cell; at 1536 px the Call Delta and Call LTP digits touch ("0.8389564.35") - spacing only, on the visual list |

## Deferred (written here; file at the land goal with `gh_issue.py app ... --stage`)

1. REQ-109 AC-7 settlement at expiry is not built. The SENSEX paper legs (strategies 52, 53, 60, 61) expire 29 Oct; after
   that they show PAUSED with the contract reason, never settled. Next: settle at the exchange settlement price (ADR-083).
2. O-1 / O-2 (walk 1, not reproduced in 8 more builds): a first quick pick showed "could not get an answer" with no API
   log line; one outcome call returned 503 to the browser while the API logged 200. Watch in the next live walk.
3. Same class as F-3, outside its fix: `backend/ofo_app/routes/execution_return.py:208` loops `plans_for` over several
   strategies (one query set per strategy).
4. In market hours the builder's IV and Greeks always run on the spot-fallback forward ("Price data: estimated from
   spot", ADR-061 label) because the builder reads only its legs, never enough strikes for a parity forward.
5. Accessibility: the Save name field and the drawer's Lots select have no accessible name.
6. Tooling: `wt-new.ps1 -Name` adds the repo prefix again if the name already has it; its node_modules linker fails when
   the main checkout has none (linked by hand to the gcbm tree's install as a junction); the `builder` agent type works in
   its own `.claude/worktrees/agent-*` tree and was refused git in a tree made for it (commits taken from its branch).
7. Tooling: builder mutant scripts edited live files in place and wrote CRLF back; the re-run used byte-exact restore
   and counted a mutant killed only on a failed test. Mutants belong on a scratch copy.
8. Round 2 review MINORs (unverified by run): a slow FAILED open of strategy B can show its error over a later-opened C
   (`StrategyBuilderPage.vue:276`); after Clear all the URL keeps ?strategy=X, so Open in Builder on X does nothing until
   a reload (`:282`); an open within one leg-edit round trip can be dropped silently (`:271`); TrackingPanel `start()` has
   no id guard (A's start reply can show under B for up to 5 s).
9. Two 5 s paper refresh loops can run on one builder page (panel + Tracked tab): the same strategy's figure can differ
   for up to 5 s; polling continues while the browser tab is hidden.
10. `?template=` links inside the builder are not followed by the new URL watcher (read by the Ready-made panel itself).

## For the owner to read (product words, no decision taken here)

- New refusal texts are "pending owner read" in `tests/errors/template_pins.json`: tracking_exit_prices_not_live (433),
  tracking_leg_already_exited (434), tracking_exit_legs_invalid (435), tracking_exit_contract_not_live (436).
- Opening another strategy from inside the builder replaces unsaved edits without asking (the Saved tab's Open already
  did this). A prompt would be a product change.
- Calendar max profit / loss / breakeven show "can't be estimated" (spec ADR-143 (1)); Sensibull shows a model estimate.
- The visual-differences table in the contract.

## OWED AT LAND (not run in this goal, by the owner's rule)

openapi drift check (`generate_openapi.py`; the file was regenerated in 1c9094a7), Playwright for the builder and the
positions page (no e2e spec for the Paper tab yet), `ruff_ratchet.py`, `coverage.py . --check`, `prepush.py`, the one
push, one PR for GC-BM + GC-BP (Spec-deviation block for ADR-201; no closing keywords), CI, `merge.py <pr>
--reviewed-sha <sha>`, the deferred issues above, migration 0027 through the normal CI/deploy path.

## Worktrees kept (could not be removed in this goal)

All 8 GC-BP builder trees are clean and their commits are on build/gcbm-must-have (checked with
`git merge-base --is-ancestor`), but `wt-rm.ps1` refuses any branch not merged into main ("100 commit(s) not in main")
unless `-Discard -MergedSha`, and the contract forbids -Discard. They go at the land goal, after the merge:
`OptionsForOptions2-gcbp-tab`, `-gcbp-paper`, `-gcbp-r1fe`, `-gcbp-f3` (unused: its builder worked elsewhere),
`OptionsForOptions2-OptionsForOptions2-gcbp-f2` (doubled name), and agent trees under `.claude/worktrees/`:
`agent-a3ec8bf2060309c83` (F-3), `agent-a5d7e179a5296faa1` (round 1 backend), `agent-aa781e0a91af4fbef` (steps 4+5,
locked by the agent tooling). The f2, tab and r1fe trees hold a `frontend/node_modules` JUNCTION to the gcbm tree's
install: wt-rm deletes it as a link; never `rm -rf` them. The gcbm worktree stays. Dev servers left running for the
owner: API PID 11976 (port 8765), Vite PID 7980 (port 5174).

## NEXT

The owner's builder order after GC-BP (memory builder-order-after-gcbp-2026-10-28): B2 speed, B6/B7 what-if, B16/B17
positions, then the LAND goal (one PR, after hours).
