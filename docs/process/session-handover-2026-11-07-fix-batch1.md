# Session handover: fix batch 1 (trustworthy rules and prices), 7 Nov 2026 03:11-13:3x IST

## UPDATE 13:2x IST: items 1+2 DONE after a reviewed round 3 and a round 4 (supersedes the PARKED lines below)
Owner present from ~09:2x; the owner's standing rule (second occurrence -> independent review -> reviewed re-approach)
was applied instead of leaving #664 parked. `feature/adjustments` tip **f1992b29** (+ this handover commit), local only.
- Round 3 (790db414, merged 6e65e6ce): entry state carries engine deltas (bs_greeks at entry spot / IV, else vol from
  the fill) and entry premiums; `entry_fallback` deleted; 4/4 mutants killed. Follow-up ae3f4d1e (merged a8406d9f):
  test_playbook_test_route expects sit.S-02 (ADJ-02 entry net delta/lot -0.0159 < 0.15 -> correctly flags); PATH-10
  `T-06-2x-credit` on the strict KNOWN list: S-02's correct 6th record hits alerts.intraday.daily_cap 6 (cap scope =
  batch 2 issues 57/59, ADR-267; the paper stop itself is never gated, REQ-170 AC-5).
- Round 4 (034e9cd9, merged f1992b29): the screen check found sit.S-02 flagged on ADJ-42 although true at entry
  (net delta/lot -0.2327): round 3 gave entry Greeks to shorts only. Now every open leg carries entry Greeks and S-02
  keeps F-71 memory. Reviewer skipped for this third red: single measured cause (stated to the owner).
- Lead runs (one file per throwaway DB) on the merged tips: rule_entry_baseline 7, playbook_test_route 11,
  adjustment_opportunities 15, ic_rules_worker_paths 9, db_gate 15, 0045 2, repair 1, ic_second_adjustment 1+1xfail,
  risk_exit 9, settings_in_force 31, worker_group_key 1 passed; adjustment_check 9 passed / 2 failed = the same 2 as
  f8425618; pure 1589 / 1550 passed.
- Screen check (f1992b29): (a) ADJ-42 T-01 already_true 0.3490, S-02 already_true 0.2065, Adjustment opportunities
  Open 0 on screen - PASS; ADJ-02 check flags T-01 0.3416, T-03 0.4103, T-09 2.7000, S-02 0.2120 (none true at entry) -
  PASS by API (the screen copy's frozen scenario clock never closes a candle, so it opens no record; record opening is
  the DB core test, `records_after_new_crossing=1`). (c) delete refused AND Undo in the fixed toast ("Strategy deleted.
  Undo" restores the row) - PASS. (b) and (d) not checked on screen: the library has no unexpired stale-feed or
  through-the-short scenario (unit tests cover both). Screenshots: `C:\Users\itsab\AppData\Local\Temp\claude-chrome-screenshots-P8hkWb\screenshot-1794037407554-1.jpg`,
  `...\screenshot-1794037491287-2.jpg`; API replies `D:\Abhay\scratch\fix-batch1\evidence-adj42-already-true.json`, `evidence-adj02-flags.json`.
- Still open on items 1+2: ADR-268 "delta taken as 1" wording line; reviewer MINOR findings (0045 downgrade lock,
  repair second run is a dry run, repair compares with today's strikes -> never `--apply` on a real DB until fixed).
- Time: ~10.5 h vs 7.5 h estimated. Biggest cost: ~2.5 h of throwaway-DB setup (~3 min per file x ~50 runs).
  Next before batch 2 (recommended to the owner): migrate a template DB once and clone it per file; baseline the
  start commit while builders build; size builders to their 80-call cap; refresh scenario dates.

---
(Original 09:3x text follows.)

Contract: `docs/process/goal-contract-fix-batch1-2026-11-07.md`. Run tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`,
branch `feature/adjustments`, start f8425618, end **c816a576** (local only: no push, no PR, no CI, per contract).
Progress log with clock-stamped lines: `D:\Abhay\scratch\fix-batch1\progress.md`.

## Verdict per item
| # | Issues | Verdict | Where |
|---|---|---|---|
| 1 | 65/89/36 (rule baseline from the DB, 0045 marker, repair tool) | **PARKED #664** (PARTIAL) | branch `park/b1-rule-baseline` = 9f4a2df1 (builder tip 533b4a84) |
| 2 | 63/64 (ADR-268 delta at intrinsic, T-01 at the short) | **PARKED #664** with item 1 (same commits) | same branch |
| 3 | 79/87/77/91 (ADR-272 stale prices) | **DONE** | merge bf65c311 (builder 119a32a5) |
| 4 | gate leftovers + openapi | **DONE** | in bf65c311; openapi e3d571f1 |
| 5 | 49/45 (ADR-266 stale leg at mid, max-loss guard) | **DONE** | merge 8c322ef7 (builder 86e6c3be) |
| 6 | 72/73 (ADR-271 paper orders block delete, Undo in toast) | **DONE** | in 8c322ef7; stale test fixed 74866cf2 (076193d7) |

**Why item 1 is parked.** The core proof PASSES (`tests_app/test_rule_entry_baseline.py`: `restart_first_check=Flag
records_after_new_crossing=1`), but after 2 fix rounds the change broke 11 tests that are green on f8425618
(`test_adjustment_check` 2, `test_adjustment_opportunities` 9). Independent review (fresh Sonnet, read-only): REGRESSION -
the stored entry state has no Greeks and no prices, so T-03 / T-09 fall back to the first check and a rule true now is
treated as true at entry (ADJ-02 entry: short CE delta 0.1691 < 0.35, T-09 41.80 vs 3.0 - neither held, both must flag).
Next round approach (in #664): entry Greeks from bs_greeks at entry spot / IV, entry premiums as prices, fallback only
without entry facts, a mutation test. Tier A review of migration 0045 + repair tool: **PASS** (3 MINOR, in #664).
**Never run `scripts/repair_rule_entry_baseline.py --apply` on a real DB** until the MINOR "today's strikes" finding is fixed.

## Evidence (commands run by the lead this session, on the merged tips)
| Claim | Evidence |
|---|---|
| Core proof passes on item 1 | `db_run_fresh ... tests_app/test_rule_entry_baseline.py` on 9f4a2df1: `1 passed in 26.94s` |
| 0045 up/down/up, repair | same tool: `2 passed`, `1 passed`; reviewer mutant M1 killed |
| Item 1 breaks 11 tests | same files on f8425618 vs 9f4a2df1: adjustment_check 2F vs 4F, opportunities 0F vs 9F |
| Worker reds are older than this batch | `test_background_worker.py` in full on f8425618: `11 failed, 7 passed in 1164.83s` (#663) |
| Items 5+6 on 8c322ef7 | domain `1583 passed`; reply inventory `24 passed`; vitest 3 files `41 passed`; DB: delete 28, tracking_list 33, opportunities 15, cycle 61, carry 4, ic_exits 9, ic_rules_worker 9, choke 13, t14 14, two_stops 13, roll_basis 15 passed |
| Items 3+4 on bf65c311 | domain + gate `1621 passed`; money baseline `9 passed`; app no-DB `39 passed`; vitest 14 files `220 passed`; DB: approaches_route 93, readers 40, opportunities 15 passed |
| Paper-delete test fixed | `test_paper_book_owned.py` on 74866cf2: `4 passed` |
| Connection-limit false red cleared | `test_two_screen_checks_write_no_adjustment_state_at_all` alone on 74866cf2: `1 passed` |
| openapi current | `tests_app/test_openapi_drift.py`: `1 passed` |
| Owner wording approval recorded | `tests/errors/test_template_pins.py`: `63 passed` |
| main untouched | `main` 4119c8c5, `origin/main` 69a2e984 at start and end |

Same-as-start failures (not this batch; red on f8425618 too): test_adjustment_check 2 (adj24b no-spot, another user's
strategy), test_adjustment_history_why 1, test_adjustment_plan 2 (stop 50 vs 30 default), test_strategy_store 3
(core proof + no-live-market column), test_background_worker 11 (#663). test_adjustment_plan_settings and the last 6
files of item 1's list were not run (the list was stopped once item 1 was parked).

## Screen check (scenario copy from the run tree, port 8766 / vite 5175, Chrome, test data)
- (a) IC past a rule level: **not checked** - item 1 parked.
- (b) Compare with stale prices: **not checked on screen** - ADJ-19 is the library's only stale-feed scenario and its
  contracts expired 3 Nov; the catalogue lists 0 contracts today, so the Builder cannot open the book. Covered by
  `test_adjustment_stale_prices.py` (15) and `adjust-compare-stale.test.js`. Needed: a stale-feed scenario with a later expiry.
- (c) Delete refused: **PASS** - My Strategies row shows "Can't delete: paper orders were placed" and no Delete; API
  DELETE -> `409 STRATEGY_VALIDATION_504`, strategy still there. Undo in the toast **not checked on screen** (a second
  draft could not be seeded: TooManyConnections for role ofo_app); covered by `my-strategies.test.js`.
- (d) T-01 at the short: **not checked** - item 2 parked.
Screenshot: `C:\Users\itsab\AppData\Local\Temp\claude-chrome-screenshots-P8hkWb\screenshot-1794023877066-0.png`.

## Owner questions
Q3 (wording read): answered 09:2x "Approve all" - 9 texts marked owner read in template_pins.json (c816a576).
Q1 (issue 80, batch 3) still open.

## Issues and findings filed
#663 deferred (worker tests red by calendar date), #664 parked (items 1+2). Findings:
`knowledge/findings/db-test-fixed-scenario-clock-vs-db-clock.json` (new), `rule-entry-baseline-taken-at-first-check.json`
(fix attempt lesson). Index regenerated (aa385a14).

## Mistakes this run (lessons)
1. I ran two DB test lists at once: they shared role ofo_app's connection limit with the owner's live app and produced a
   false red (`TooManyConnectionsError`). One DB list at a time.
2. My first "is it pre-existing" check ran one test alone; the worker reds only show in full-file runs. Baselines run
   the same scope as the failing run.
3. Contract budget 120 calls exceeded the builder cap (80); item 1 needed 4 builder runs.

## Left behind (not removed)
- 9 agent worktrees of this run (`.claude\worktrees\agent-af338cda...`, `-af0dda26...`, `-a2a59b01...`, `-a5b8f581...`,
  `-a6720a83...`, `-ad7a9ec5...`, `-aa2f7e77...`, `-a8550abe...`, `-a14e184c...`): `wt-rm.ps1` refuses ("-MergedSha is
  not on origin/main") because nothing may be pushed. Remove after the owner-approved push; TTL 48 h.
- 36 older `ofo_test_tmp_*` databases on the DB host (31 Oct - 7 Nov): `python scripts/orchestrator/db_run_fresh.py --sweep`
  drops those older than 24 h.
- Scratch: `D:\Abhay\scratch\fix-batch1\` (logs, scenario_stack.py copy, seed tools).

## Next
1. Owner: approve a push of `feature/adjustments` (c816a576) if wanted; then remove the worktrees.
2. Item 1+2 round 3 per #664 (merge feature/adjustments into `park/b1-rule-baseline` first, record the merge in #664).
3. Batch 2 contract (alerts and exit safety), per `docs/process/fix-plan-2026-11-07/batches.md`.
