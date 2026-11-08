# Goal contract: fix batch 1 - trustworthy rules and prices (2026-11-07)

**Status: APPROVED by the owner 2026-11-07 ~03:xx IST** (question tool: "Save the plan and create goal contract to work
on batch 1 now"). Development of batch 1 is started by this contract; batches 2-6 each get their own contract later.
**Executor:** `/goal` in a fresh session of this project. **Run tree:** `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`,
branch `feature/adjustments` (start commit: the commit that adds this file). **Plan:** `docs/process/fix-plan-2026-11-07/batches.md`
(batch 1 row) with the reviewed minutes in `plan-v5-estimates.md` and file:line in `code-checks.md`.

**Mission:** fix batch 1's issues on `feature/adjustments` with code + unit tests of the changed code + tests of the
direct importers, then one on-screen check on test data. Done = every item below accepted, the batch's impact tests
green on the merged tip, the screen check recorded, handover written. NO PR, NO CI, NO push, NO full prepush gate
(owner 2026-11-07). Nothing to main.

Core: the background worker's rule memory comes from the DB, so a crossing that existed at entry is not raised as new.
Proof (step 1, before any other item is built): on a THROWAWAY DB (`scripts/orchestrator/db_run_fresh.py`), a paper IC
entered with spot already past a rule level -> worker restarted -> first cycle writes 0 opportunities for that rule; a
later move that newly crosses it writes exactly 1. Counted from the DB by a test (`tests_app/`), output read back.

## §0 Run rules (carried from goal-contract-ic-e2e-paper-2026-11-05.md §0.1, §0.4, §0.5; read them there)
1. Lock: `D:\Abhay\scratch\fix-batch1\.run-active.lock` with this session's id + start time; another session's lock = stop.
   Delete it as the last action (DONE, PARKED or HALT).
2. The owner's live app (8765, `ofo_dev`, frozen tree `D:\Abhay\Ventures\OptionsForOptions2-live`) is never touched:
   no edit, merge, checkout, restart, or DB write there. All proofs use `db_run_fresh.py` throwaway databases.
3. Branch: all work lands on `feature/adjustments` in the run tree; builders cut branches from the batch start sha in
   their OWN worktrees and are merged back BY SHA (the builder's reported sha). No push, no PR, no `gh pr`. main
   checkout and `origin/main` tips recorded at start and end; any change = HALT.
4. Disk: C: and D: at least 10 GB free before dispatch (`Get-PSDrive C,D`). Memory: at least ~1.5 GB free per builder
   before each dispatch; below it, dispatch fewer at once.
5. Processes: stop only PIDs this run started and recorded; never select a process by command-line text.
6. Owner asleep: no AskUserQuestion. A spec-conformant choice is decided and recorded (decision row or handover line);
   anything needing the owner goes to `docs/process/owner-questions-2026-11-07.md` with a recommendation, and the run
   continues with the safe default.
7. Park rule: an item red after 2 fix rounds is PARKED (issue via `gh_issue.py app ... --stage`, label `parked`, evidence,
   what is left); the batch continues; the item stays PARTIAL.

## Scope (batch 1 only)
| # | Issues | Fix (smallest, per code-checks.md + review) | Builder | Min |
|---|---|---|---|---|
| 1 | 65 / 89 / 36 (finding `rule-entry-baseline-taken-at-first-check`) | seed worker rule memory from `playbook_store.rule_state` on the REBUILD path (`GateLoad`, background.py:553-560, 625-639; `test_background_db_gate` enforces this), baseline stored at entry, ADR-258 re-baseline after an adjustment (new migration; 0031 guard forbids deletes / `held_at_entry` changes - add a marker, never rewrite); re-runnable repair of rows written after a crossing (counted, dry-run first) | Opus | 180 |
| 2 | 63 / 64 (ADR-268) | delta 1/0 at intrinsic (adjustment_check.py:194-196); T-01 fires at / beyond the short (playbook_eval.py:458-461) + wording | with 1 | 55 |
| 3 | 79 / 87 / 77 / 91 (ADR-272) | reuse `prices_fresh` (adjustment_check.py:187-192) + add the "as of" time; approaches reply carries stale + age; no leaders when stale; Prepare disabled + banner in AdjustCompare; Pause box / TrackingPanel read `withheld` (routes/adjustment_check.py:100); a test of the 14:30 time-exit clock (`exit_inputs_of`); limit as a registry setting only if the `alerts.`/`adjustments.` prefix already covers it, else a constant + handover line | Sonnet | 190 |
| 4 | gate leftovers | `tests/orchestrator/test_select_app_tests.py:60-75` PR241_SELECTION + `test_leg_edit_db_trips.py`; strategy-table / strategy-live baselines for StrategyBuilderPage.vue :143/:651/:658 (line-text baseline entries with reason); regenerate `docs/api/openapi.json` LAST, after all merges | with 3 | 35 |
| 5 | 49 / 45 (ADR-266) | mark a stale leg at bid-ask mid (adjustment_check.py:278-283); marked loss above max loss -> "not checked" with reason (`_stop_hit`, playbook_eval.py:702-715); measure first where a per-option quote time exists (only DayStats.last_trade_ts, kite_frames.py:67): if none, stale = LTP outside bid/ask | Sonnet | 110 |
| 6 | 72 / 73 (ADR-271) | `_CAN_DELETE_SQL` (strategy_store.py:115-116) adds NOT EXISTS paper orders + reason text; Undo inside the fixed toast where the user clicked | with 5 | 75 |
Waves: builder 1 (items 1+2) starts with the Core proof; builders 2 (3+4) and 3 (5+6) start at the same time (they do
not depend on the core). Items 1, 3 and 5 all touch `backend/ofo_app/adjustment_check.py`: merge order 1 -> 5 -> 3,
re-running the impact tests after each merge.

**Out of scope:** every other issue in the plan (batches 2-6); PR, CI, push, full prepush, e2e/mutation runs, phone
width, live market, real orders, main.

## Testing (owner 2026-11-07: only what changed and its impact)
1. Builder: the changed files' own test files + tests of DIRECT importers (grep imports; `python tools/graph.py
   affected --files <path>` is a hint only, it is transitive and over-wide). DB tests one file at a time via
   `db_run_fresh.py`. Frontend: vitest on the touched test files. Output to a log, tail read.
2. Lead, after each merge: re-run that builder's test list on the merged tip (a worker report is a claim).
3. Migration (item 1): one fresh Opus reviewer, read-only, Tier A (kit 1.21 `**/alembic/**`), 25 min / 40 calls:
   upgrade + downgrade + guard + grants + the repair tool's dry run. MAJOR findings fixed in at most 2 rounds.
4. Screen check (end): the scenario copy of the app from the RUN tree (copy `D:\Abhay\scratch\ic-uitest\scenario_stack.py`
   to `D:\Abhay\scratch\fix-batch1\` with `LIVE` = the run tree; port 8766; throwaway DB; frontend vite from the run
   tree on a free port proxied to 8766) in the owner's visible Chrome (Claude-in-Chrome), desktop width only:
   (a) IC entered past a rule level shows no new alert, a new crossing shows one; (b) Compare with stale prices shows
   the stale banner, no leaders, Prepare disabled; (c) a strategy with paper orders cannot be deleted and the toast
   says why, Undo in the toast; (d) T-01 at the short. Screenshots + one line each in the progress log. Never click
   inside a live order panel; test data only.

## Builder briefs carry
`Budget:` (Opus item 1: 120 min / 120 calls; Sonnet: 90 min / 80 calls), `Report: evidence-table`, `Why Opus:` for
builder 1 (DB migration + background rebuild path + data repair), `Class:` and `Proof:` (each item is a defect fix: RCA,
class as a data filter, failing test first, class-level fix, one real-data proof on the throwaway DB or the scenario
library, detection change or `No detection change: <reason>`), the `.claude/kit/builder-brief.md` standing items, the
item's file:line from code-checks.md and the reviewer findings in plan-v5-estimates.md, a Reuse list (grep existing
code first), and `Graph brief:` = the `graph.py affected --files` output for the item's files (no W-item exists).

## Progress log and final report
Log: `D:\Abhay\scratch\fix-batch1\progress.md` (clock-stamped lines: dispatch, merge sha, test list + result, park).
Final report (handover `docs/process/session-handover-2026-11-07-fix-batch1.md`): DONE / PARTIAL / PARKED per item
with the evidence table (command + result line), merge shas, migration review verdict, screen-check lines, owner
questions filed, worktrees removed (`wt-rm.ps1`, tracked + installed package counts before/after), next = batch 2
contract. Update memory START HERE line.
