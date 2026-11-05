# Session handover: iron condor end to end on paper (goal contract ic-e2e-paper, 2026-11-05 18:42 to 2026-11-06)

DRAFT started 2026-11-06 00:31 IST while the last DB runs drain; finished at Stage D. Contract:
`docs/process/goal-contract-ic-e2e-paper-2026-11-05.md`. Progress log (every step, with commands):
`D:\Abhay\scratch\ic-e2e\PROGRESS.md`. Branch `feature/adjustments` only; main untouched (4119c8c5 at start).

## DONE / PENDING / BLOCKED / PARKED / NEXT
(filled at Stage D)

## Per stage
| Stage | State | Commit merged | Evidence (command + result line) |
|---|---|---|---|
| A core | DONE | 9e8e4eae (ff) | core proof `1 passed in 189.60s` (lead, 14573227); scope readers `4 passed in 34.07s` (lead, 9e8e4eae); review REVISE -> MAJOR fixed with a killing test |
| B2 T-14 | DONE (scenario mode only) | a36bbb88 (merge of ee7dbaab) | worker DB `2 passed in 41.56s`; lead non-DB `124 passed`, `46 passed`; review REVISE -> F1/F2 fixed |
| B3 14 approaches | DONE | 2ba290a2 (ff) | DB `18 passed in 456.99s`; lead A-11 guard mutant `2 failed, 8 passed`, restored |
| B1 rules | (pending) | | |
| B4 bell + toast | (pending merge after the opportunities fix) | | |
| B5 wording + 0044 | (pending) | | |
| C1 / C2 / C3 | (pending) | | |

## Owner decisions this run
- 2026-11-06 ~00:3x (question tool): "Changed tests only": after each change only the test files it adds or edits plus
  the stage's one acceptance test, once; no select_app_tests list per change or merge, no full suites, no mutation
  runs, no PRs, no CI; one prepush --full at the end. Written to the ic-e2e plan (2b) and memory. No spec change:
  process answer.
- Parked for the owner: owner-questions-2026-11-05.md (f) T-14 on LIVE strategies (run keeps it scenario-only).

## Findings registered (knowledge/findings/)
- approach-name-list-split-from-built-list (T-19 line lost the approach name + cost for 8 approaches; fixed)
- background-trigger-without-the-inputs-it-needs (T-19 never checked by the worker, live too; parked)
- entry-day-from-the-database-clock (S-12 entry day from created_at; parked)

## Issues filed
- #659 deferred: scenario-mode data routes accept a live strategy id.
- #660 deferred: flaky test_feed_control bus count (fix builder dispatched 00:3x).

## Process lessons (proposed, not applied)
1. Stage acceptances were written as DB tests against the plan's "DB runs only twice": ~25 DB runs on one lock, builders
   idle for hours. Count DB runs in the plan before approval (memory updated).
2. Each db_run_fresh run spends ~3.5 of ~7 min on CREATE + 44 migrations: a template-copy runner
   (D:\Abhay\scratch\ic-e2e\db_tmpl.py, written, NOT proven) would cut that to seconds. Build + prove it in daylight.
3. prepush --full runs no DB test and CI runs only on main, so on a feature branch DB tests run only by hand
   (the 8 opportunities failures from GC-IC1 hid this way).
4. dblock v1 was not first-come-first-served (B4 waited 17 min); v2 uses a ticket queue.
5. A builder typed `python -` three times (one wrote 315 MB): propose a PreToolUse guard refusing a bare `python -`
   with no heredoc body.
