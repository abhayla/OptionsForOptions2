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
- Frontend vitest on 711cc107: 78 files, 1260 passed.

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

## OWED AT LAND (not run in this goal, by the owner's rule)

openapi drift check (`generate_openapi.py`; the file was regenerated in 1c9094a7), Playwright for the builder and the
positions page (no e2e spec for the Paper tab yet), `ruff_ratchet.py`, `coverage.py . --check`, `prepush.py`, the one
push, one PR for GC-BM + GC-BP (Spec-deviation block for ADR-201; no closing keywords), CI, `merge.py <pr>
--reviewed-sha <sha>`, the deferred issues above, migration 0027 through the normal CI/deploy path.

## NEXT

The owner's builder order after GC-BP (memory builder-order-after-gcbp-2026-10-28): B2 speed, B6/B7 what-if, B16/B17
positions, then the LAND goal (one PR, after hours).
