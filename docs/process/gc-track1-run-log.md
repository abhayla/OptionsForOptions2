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
- 2026-11-12 07:39 IST owner (in chat): "Have you completed everything that needs to be completed without kite login? ... Till then, don't sit idle." -> read as permission to run tasks that do not depend on the k04 outcome before it: k16, k17, k20, k22-k27 (5 builders, worktrees -dadj/-dfront/-dsup/-ddb + the main gc-track1 tree). B1 (k06-k09), k11-k15, k08, k10 still wait for k04 (they build on what it proves).
- 07:44 k17 done a8654c7f (8 passed, re-run); k27 done f495b6c8 (red 'Received: 6 legs', then green, re-run 70 passed); k20 done with no code: existing order_path switch (off unless APP_ENV=test) already hides every Execute and the execute route, tests 44 passed. TODO: ADR-292 (6) wording -> name the order_path switch and the real label 'Open Kite to place these orders' (there is no 'Send to Kite' text).
- 07:52 k22 done 33f9ed5b (session re-run 245 passed). k26 PARKED #699 after 2 rounds: r1 51fdb62f merged the shown review lines (ADR-274 (3)); r2 6e843923 combined paper orders as one oversize 'exit'. Neither merged. Stage line committed 90ce1f7b on -dsup.
- 08:16 k23 c6a0e82f + k16 3ec84d21 accepted (session DB run test_background_worker.py 23 passed via main-checkout db_run_fresh with the worktree as run folder; a worktree has no .env, so 'db_run_fresh.py .' fails at once - not a result). k24 bddf36b2 + k25 1f1cdf2f red-then-green by the builder; test_paper_monitor.py running. Merged by sha into build/gc-track1: f495b6c8 (k27), d41c6b0b (k17 + #699/#700 stage lines), 33f9ed5b (k22).
- 08:47 owner asked whether I would wait for the market or keep working. Decision (technical, mine): start B1 (k06 migration + k07 route) before k04, in worktree -b1. Reason: the watcher already checks 5 paper strategies (log 08:43 '5 strategies monitored'), B1 stores a held condor as plain paper orders + one row and does not change how the watcher reads it; worst case if k04 fails ~30 min of builder work. Kite connected 08:44 (kite socket connected 08:44:10). k04 spike at 09:17.
- 10:58 k04 CORE PROOF PASS (watcher reads a typed-in condor on live prices): held condor strategy 136 (NIFTY 17 Nov 25650/25750 CE, 25050/24950 PE, typed at live LTP, stated entry 10:30) saved 10:44:58 with no app page open; worker '6 strategies monitored' from 10:48, recomputes {136: 2} every minute 10:47-10:54 on 4 legs, reads FRESH 300-318; adjustment_rule_state 16 rows for 136 (held_at_entry false on all, seen_clear true on 12). k05 measured cause: public.strategy_basket_facts has 0 rows for 136 - record_basket_facts reads the spot from the API's own provider, which holds no index quote without a page socket, and returns silently (finding entry-facts-skipped-when-the-api-holds-no-index-quote); rules needing entry ATM IV read not_checked. -> k08 fixes it. Spike fixes on the way: the REST chain is NOT_CONNECTED by design without a socket (read over the chain socket instead); the API started before the login (08:31) had to be restarted (10:44, PIDs 22164/6692).
- 12:11 k18 PASS ([LIVE], 30 min 11:41-12:10, no screen open): worker minute lines - typed-in condor 136: 59 checks (2/min, 1 at 12:02), paper condor 128: 59 checks (2/min, 1 at 12:04), every minute > 0; reads FRESH except 12:07 (FRESH 306, STALE 42); one alert raised with no page open: 'opportunity strategy=128 rule=T-03 record=263 written 11:45:01'. Limit: 136 has no held row (the live app runs main, which has no held store yet).
- 13:00-14:26 k29 Tier B review REVISE: 1 MAJOR (the daily cap count restored on worker start includes exempt
  records) -> k22 round 2 41d144c3 broke tests_app/test_risk_exit_not_gated (paper route reached alert_gate through
  playbook_store) -> reverted 295e3ad1, parked #702; E501 docstring wrapped 51159d51. Prepush red runs on the way:
  openapi stale (regenerated b67e0743), broker-name scan (allow-list line 3225b298), the risk-exit guard. k30 prepush
  TOTAL PASS 1840.6s on 51159d51.
- 15:06 k19 PASS ([LIVE], owner's visible Chrome, app screens only, no Kite page): Compare on the typed-in condor 136 (prices 15:04:34, spot 25258.15 live) listed 9 approaches; chose 'Roll the untested spread toward spot' (credit +391.30 per the table); Open in builder -> 4 pending changes -> Review paper orders (exit BUY 25650 CE + exit SELL 25750 CE at server price, add BUY 25650 CE 59.50 and SELL 25550 CE 81.25 typed) -> Confirm. After: 0 pending, net positions 25650 CE long @59.50 (booked +2437.50 on the closed short), 25550 CE short @81.25, 25750 CE closed booked -1816.75, puts unchanged; total P&L +45.50, charges 280.14. Screenshots: claude-chrome-screenshots-7SyYNz/screenshot-1794476111220-0, -1794476160330-1, -1794476168372-2 (local, not in the repo).
- 15:16 owner (in chat): 'Wherever you have question, go with your recommendations' -> A2 answered as recommended: migration 0052 applied to ofo_dev (alembic current 0051_trigger_label_words -> 0052_strategy_held_entries (head)); API + background + vite restarted from the build branch tree (PIDs 25924/15308, 17700, 11812). Held condor strategy 137 typed in 15:14:31 with the held block (entry 15:00, broker Zerodha): DB shows strategy_held_entries row, strategy_basket_facts basket 0 at 15:14:32 with spot and IV (k08 live proof: facts stored with no page open), 4 paper orders. k10 screenshot (Positions > Paper, card 'Held IC k10'): 'Held at my broker', 'Entry 12 Nov 15:00', 'Rules start from 12 Nov 15:14', 'Zerodha', record-here line - screenshot-1794476761172-3 (local).
- 16:37 k31 PR #703 merged by merge.py --reviewed-sha 51159d51 (8 checks pass; api 2h08m, near its 150-min limit -> raised to 180 in the handover PR). Live app restarted from main 16:38 (health healthy, Kite connected).
