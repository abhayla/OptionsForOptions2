# Session handover 2026-10-15 (c): W-065 and W-071 done, all Stage 4b questions decided

Plan: `docs/process/goal-contract-2026-10-15.md`; master plan `master-plan-2026-10-07.md`. Owner present in the evening.
Previous handover: `session-handover-2026-10-15b.md`.

## DONE (merged; CI green on every PR)
| PR | What |
|---|---|
| #233 | docs batch: final 15:46 tick summary, W-065 p3 briefs, finding liveness-from-shared-subscribers, #232 row |
| #235 | **W-065 done** (Tier A): Builder live socket; not-live fallback on the page's OWN drop (`fallback` flag). Round 1 FAILED (another tab on the same legs kept unlabelled numbers on screen, frozen after ~3 min); round 2 PASS; LOWs in #234 |
| #236 | docs batch: 4a gate review draft, finding builder-budget-is-prose (Startup-Factory#98), briefs |
| #238 | Stage 4b Q263-Q270 numbered; Q263 (ADR-079) + Q266 (ADR-081) owner answers; Q264/Q265/Q268 expert decisions (ADR-080) |
| #239 | Q267 (ADR-082 + F-35: charges from Zerodha's published rates; money sentences include charges), Q269 (ADR-083 expiry), Q270 (ADR-084 grouping) |
| #241 | **W-071 done** (Tier B): Save Draft + reopen; `contract_id` / segment+token bridge (ADR-057, card class 1); reprice prompt wording ADR-085 (owner) as pinned template; core proven on ofo_dev's real catalogue; browser save e2e is skipped in CI (#237) |

Also: `ofo_dev` now holds today's real public instrument list (7,397 rows; it was EMPTY, so the 4a gate re-run would
have found no catalogue). New helper `scripts/orchestrator/dev_run.py` (DATABASE_URL = ofo_dev, refuses anything else).

## RUNNING
- **Token-expiry watcher** PID 14884 since 15:50:34 (`docs/research/kite-proof-2026-10-07/token-watch-2026-10-15.json`,
  every 15 min, every minute 04:00-09:00). Keep the laptop on mains power (battery sleep = 1 h).

## NEXT (2026-10-16, in order)
1. Read the watcher JSON (`first_fail` = the expiry minute) -> F-id in `spec/findings.md` + commit the JSON.
2. **4a gate re-run** (`docs/process/gate-4a-review-2026-10-15.md`; the 11:55 run predates #212/#211/#216): one owner
   Kite login in a PRIVATE window; API on 8765 via `dev_run.py`; D8 incl. TOTAL rows; draft save -> reopen through the
   screen (W-071); 8 screenshots on current main; copy results into the repo; write the verdict.
3. #232 items 2-4 (broken message fragment, raw instrument ids, raw ISO times) - decide in the gate review.
4. #242 mechanism (atool runs tests_app files referencing a changed route) - small, before the next app change.
5. Stage 4b build items from ADR-079..084 and #240 (charges in the engine, Tier A) - only after the 4a gate passes.

## PARKED / DEFERRED
- #200/#199 (REQ-065 open exception, ADR-074). Deferred: #213, #220, #221, #234, #237, #240, #242.

## Misses (recorded)
- Builders overran call budgets 4 times on 2026-10-15 (finding builder-budget-is-prose, Startup-Factory#98). Briefs
  saying "hard limit; count your calls; at N-3 commit and report" held the next three rounds (23/30, 9/20, 17/30).
- A builder reported "generate_openapi.py produced no diff" while `openapi.json` was stale (caught by the verifier).
- targeted-tests-miss-dependent-files, 4th occurrence: W-071's new response fields broke two app tests in other files;
  caught by CI (#242). My fix brief then had the fixer run 11 files (488 tests, 15 min) on the production-host test
  database - more than "targeted only" allows; the #242 selector must pick only files that reference the change.
- I wrote ADR-085 with an unquoted colon (invalid YAML); the local mirror caught it before push.
- Q267 was asked as one question with two parts (source and sentences); the owner's answer needed a follow-up.

## Not in git (this PC)
- A stale `merge_when_green.py 97` process (PID 24052, not this session's) was left running.
