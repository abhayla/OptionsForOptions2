# Brief: GC-MU A3 round 2 - Dismiss on the inbox row (ADR-230 (2) "dismissing the row there clears the mark")

Core: an open group in Positions > Adjustment opportunities offers Dismiss (optional reason from the server's closed list); dismissing it calls the existing dismiss route for that group's open records, the row shows "You dismissed this", and the Live Strategies card mark for that strategy drops (0 -> no mark).
Proof: step 1 of this brief - a vitest on `AdjustmentOpportunitiesPage.vue` with a fake client: an open group with records 4, 5, 6 shows Dismiss; clicking it posts `/adjustment-opportunities/4/dismiss`, `/5/dismiss`, `/6/dismiss` with the picked reason, then reloads the list.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 2/2
Class: a decision's user path missing from the screen it names. ADR-230 (2) says the user dismisses "the row there" (the inbox); measured 2026-11-01 in the owner's Chrome on scenario ADJ-03: the inbox row has only "Compare approaches", and Dismiss exists only in `frontend/src/components/strategy/AdjustDrawer.vue:53-62` (the tracking panel's drawer). Population: every open inbox group; before: none can be dismissed there; after: all can.
Proof (class): the vitest above plus one for a group with no open record (no Dismiss shown) and one for a refused dismiss (the server's refusal text shown, the row unchanged).
Spec quote: ADR-230 "dismissing the row there clears the mark"
Sensibull: n/a - the reference product has no adjustment-opportunity inbox (searched the study for opportunity, dismiss).
Reference: none - searched adjustment opportunities, dismiss (no screen); open records: RD-096 (shape detection, not touched)
Copy from: none - reuse this repo's own `AdjustDrawer.vue` dismiss code (lines 110-135): same reason list (`dismiss_reasons` from `GET /adjustment-opportunities`), same post, same error display.
Tier: B (Sonnet diff review by the orchestrator; vitest is the gate).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-inbox`, branch `build/gcmu-inbox` (from `build/gcmu`). `frontend/node_modules` is a junction to the run tree's: never delete it, never run `npm ci` / `npm install` / `npm run build`. Change `frontend/src/pages/AdjustmentOpportunitiesPage.vue`, `frontend/tests/adjustment-opportunities.test.js`, and (only if a shared helper is cleaner than a copy) a small new `frontend/src/lib/` helper used by both the page and the drawer. No backend change, no new wording (reuse the drawer's existing texts and the server's reason labels). Commit there only, never push.

## Do, in order
1. The failing vitest first (open group -> Dismiss -> three posts with the reason -> list reloaded), see it red, then build.
2. Answer states, one test each: group with open records (Dismiss shown); group with none open (no Dismiss); reasons list failed to load (Dismiss still works with no reason, as the drawer); a dismiss refused by the server (its refusal text shown, nothing else changed); one of three posts fails (the others stay dismissed, the error shown, the list reloaded so the row shows the truth).
3. Run: `npx vitest run tests/adjustment-opportunities.test.js` and the drawer's spec (grep `AdjustDrawer` in frontend/tests) from `frontend/`, plus `npx eslint` on changed files if the repo lints (see `package.json` scripts). Logs to a file, tail only. Guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan` (the T1 money-arithmetic scan covers the frontend).

## Standing items
- The browser computes nothing (counts come from the server); no money arithmetic in the page.
- If `git commit` is refused by verifier_inflight_gate, wait ~2 min, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-inbox.
