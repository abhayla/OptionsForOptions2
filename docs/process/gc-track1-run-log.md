# GC-TRACK1 run log

Contract: `goal-contract-GC-TRACK1-2026-11-12.md`. Status rows k01..k32 on the project status page. Times are IST,
read from the clock.

## 2026-11-12 (Thu, trading day per `backend/ofo/market_calendar.json`; started 00:31)

- Start 00:31: main `70bd2b61`; no k-row existed; no row's done line held on main. Owner away (night): questions go to
  `owner-questions-2026-11-12.md`. [LIVE] rows (k04, k18, k19) wait for 09:15.
- k01 00:32: rows k01..k32 created (one batch, 32 writes, order 301..332).
- k02 00:33-: docs commit 19c02941 + digest c9e7e285 on `docs/owner-goal-2026-11-11`. Local CI mirror:
  14 passed, 2 failed (both = stale `views/spec-digest.md`: ADR-290/291 were new and the digest was not regenerated
  with them); regenerated, `build_spec_digest --check` current, `kit_drift` 94 ok / 0 edited. The push guard asked for
  a `prepush.py` marker; its preflight first failed on an incomplete `frontend/dist` (no `.vite/manifest.json`) in
  the main checkout, rebuilt with `npm run build`, gate re-run.
- k04 preparation (no code of stages B-E): spike `k04_spike.py` (scratchpad) uses the existing save path
  (`POST /strategies` with typed legs + `captured_at` 09:20, then `POST /paper/strategies/{id}/orders` at the typed
  prices). Read-back plan: worker minute lines (`recomputes` per strategy id, `reads`, `outcomes`) and
  `adjustment_rule_state.held_at_entry` per rule of the new strategy. Note: the paper-order route captures the entry
  market at the fill (`entry_facts_now`, ADR-283), so a rule-start at save time may already exist for paper orders.
- k02 01:14: PR #698 merged by `merge.py 698 --reviewed-sha c9e7e285` (4 checks pass, coverage included); main
  `6727b624`. Pre-push gate `TOTAL PASS 1230.2s`. Main checkout back on `main`, clean.
- k03 01:16: worktree `D:\Abhay\Ventures\OptionsForOptions2-gc-track1`, branch `build/gc-track1` at `6727b624`
  (`wt-new.ps1`, TTL 48h). Tool defect found and fixed: `wt-link-modules.ps1` searched a hard-coded folder list
  (`web`, `scraper`, `packages\shared`) and linked nothing for this repo's `frontend\node_modules`, so any front-end
  test here would have failed as "module not found". Now it finds every first-level folder holding a
  `node_modules`; re-run: 206 of 206 entries linked, `frontend\node_modules\vitest` present. `wt-rm.ps1` already
  finds such folders generically (its `Get-NmRoots`), so removal deletes them as links.
- k21 01:19-01:21: fix-list triage (`fix-plan-2026-11-07/ic-test-issues-snapshot.md`, items 1-91; phone-width items
  50, 51, 53, 54, 76 out by the desktop-only rule). Read by two read-only checkers (Sonnet, halves 1-46 / 47-91,
  citations per row); the lead re-read the deciding lines of every picked item and of the demoted ones.

  Fixed or not open on main: 1, 3, 6, 10, 19, 24, 25, 29, 31, 34, 36, 45, 49, 56, 58, 63, 64, 65, 67, 69, 72, 73, 74,
  75, 77, 79, 81, 87, 89, 91 (commits and handover lines in the checkers' tables; e.g. 65/89 = 49f8c025 + ADR-283
  3649c17a, 63/64 = f1992b29 / 9f4a2df1, 81 = af4527ed).

  | Item | What the owner would see wrong | Class | Tracked condor? | Pick |
  |---|---|---|---|---|
  | 57 | a level watch he set is held by the daily alert cap (no alert) | DEFECT | yes | k22 (with 60) |
  | 60 | a day rule (Friday carry check) held or dropped by the cap | DEFECT | yes | k22 |
  | 33 | a new strategy's first alert comes one candle late | DEFECT | yes | k23 |
  | 59 | a day-rule alert row with an empty "What happened" | DEFECT (unclear on main) | yes | k24: test first; if green, recorded fixed and the slot goes to 40 |
  | 11 | the alert list and bell keep alerts of deleted strategies | DEFECT | yes | k25 |
  | 80 | A-01 suggestion trades the same contract twice (ADR-274) | DEFECT | yes | k26 |
  | 40 | paper list "6 legs" counts closed legs | DEFECT | yes | k27 |
  | 23 | exits counted as adjustments | by design (ADR-255: partial exits count); only Exit all miscounted, which closes the strategy | yes | no |
  | 47 | builder's planned credit from stale prices (ADR-265) | DEFECT | no: paper fills use the live price (item 6 fixed); preview only | deferred |
  | 20 | a 3-leg shape gets no rules and no message | needs a new generic trigger set | yes | DEPTH (frozen: no new trigger) |
  | 41 | one unpriced old book blanks the paper summary | needs a SPEC CHANGE ("never a partial sum") | yes | deferred, owner call |
  | 70, 17 | builder "no live quote" in bus mode after close | DEFECT, cause unknown | no | deferred |
  | 78 | zero max profit says "not finite" | wrong text | no | deferred |
  | 88, 90 | T-11 at the limit; raw `day.*` text | probably fixed, unverified on screen | yes | deferred (verify) |
  | 16 | exit dialog "no answer" then a second click exits twice | unclear (pool fixes cover the cause) | yes | deferred (verify) |

  DEPTH (frozen by standing direction rule 2): 2, 4, 5, 7, 8, 9, 12, 13, 14, 15, 18, 20, 21, 22, 26, 27, 28, 30, 32,
  35, 37, 38, 39, 42, 43, 44, 46, 48, 52, 55, 61, 62, 66, 68, 71, 82, 83, 84, 85, 86. Unclear, never located by the
  checkers: 2, 5, 8, 21, 26, 27, 46 (all DEPTH, so no fix depends on them).
