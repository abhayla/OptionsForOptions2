# Goal contract GC-MERGE1: everything onto main, nothing left lying around (2026-11-07)

**Status:** APPROVED by the owner 2026-11-07 (Q1 "Merge now, as is"; Q2 "Triage: merge recent, archive closed").
**Executor:** `/goal` in a fresh session of this project. **Run tree:** settings tree, branch `feature/adjustments`.
**Mission:** origin/main holds everything on feature/adjustments plus the recent unique branches. Then the repo has
exactly one worktree (the main checkout), one local branch (`main`), one remote branch (`origin/main`), zero stashes and
zero stale locks. Every other piece of code is either provably in main or kept as an archive tag, and listed in the
report.

Core: a merge of origin/main into feature/adjustments that passes `prepush.py --full`.
Proof (step 1, before any cleanup): the merge commit exists in the settings tree, `prepush.py --full` writes its marker
for that HEAD, and `alembic heads` prints exactly one head. If this fails after 2 fix rounds the run HALTS, because
nothing else in this contract is safe without it.

## §0 Run rules
1. Lock `D:\Abhay\scratch\gc-merge1\.run-active.lock` (session id + start time). A live lock from another session means
   stop. Delete the lock as the last action.
2. Before anything is deleted: `git bundle create D:\Abhay\scratch\gc-merge1\all-refs-2026-11-07.bundle --all`, then
   `git bundle verify`. Write `manifest.csv` with one row per local branch, remote branch, worktree and stash: sha,
   ahead-of-main, unique non-merge count, cherry `+` count, PR number + state, category, action, and the result
   (filled in later). If either step fails, HALT.
3. Owner away: no AskUserQuestion. Questions go to `docs/process/owner-questions-2026-11-07-merge.md` with a
   recommendation, and the run takes the safe default (archive, never delete unique code).
4. Never delete a ref whose content is not provably in origin/main or in a pushed archive tag. "Provably" means
   `git merge-base --is-ancestor <sha> origin/main`, a cherry with no `+` lines, or an equal merge-tree result.
5. Worktrees are removed ONLY with `~/.claude/tools/wt-rm.ps1` (never `rm -rf`, never a bare `git worktree remove
   --force`). Before and after every removal, count tracked files and installed packages
   (`frontend/node_modules`) in the main checkout. A mismatch, or exit code 4, means STOP THE LINE.
6. The live app (8765 / ofo_dev / `-live` tree) is untouched until §5. Stop only PIDs this run started or that it
   identified by port owner. Never select a process by command-line text.
7. Push only with a passing prepush marker. Merge to main only with `merge.py <pr> --reviewed-sha <sha>`, chained with
   `&&`. Park rule: a red class that survives 2 rounds goes to an independent reviewer (second-occurrence rule); if it
   is still red, HALT with a report. The merge is never forced.
8. Stamp every progress line with the output of `date`. Log to `D:\Abhay\scratch\gc-merge1\progress.md`.

## §0b Backup push of the unpushed commits (FIRST action after the lock and bundle; owner 2026-11-07)
The settings tree's `feature/adjustments` holds 83 commits that are not on origin (82 from fix batch 1 and earlier,
plus this contract's commit). Count them: `git rev-list --count origin/feature/adjustments..HEAD`. Push them before
§1, so a disk failure during the run cannot lose them:
1. Settings tree clean (`git status --porcelain` empty); record HEAD.
2. `python scripts/orchestrator/prepush.py > D:\Abhay\scratch\gc-merge1\prepush-0b.log 2>&1`; read the tail. PASS
   writes the marker for HEAD.
3. PASS -> `git push origin feature/adjustments` (a fast-forward; never `--force`). Prove it:
   `git rev-list --count origin/feature/adjustments..HEAD` prints 0.
4. FAIL -> do NOT bypass the gate. Fix the red step in at most 2 rounds (commit, re-run, push). Still red: push the
   commits to a backup ref with `PREPUSH_GATE_ALLOW="GC-MERGE1 0b backup of unpushed commits, gate red: <step>" git push
   origin HEAD:refs/heads/backup/feature-adjustments-2026-11-07` (a backup ref, not the branch, so nothing reads it as
   gated). Log the red step, then continue; §2.3 must still pass before anything merges. Delete that backup ref in §4.3.

## §1 Inventory (read-only, ~20 min)
Fill in manifest.csv (§0.2). The categories:
- **CONTAINED**: sha is an ancestor of feature/adjustments or main, or the cherry check shows nothing missing. Action:
  delete after §4.
- **MERGE**: unique, last commit on/after 2026-11-01, never in a PR. Expected: build/merge-preflight,
  docs/ic-e2e-audit-2026-11-07, fix/cfg-source-chips.
- **ARCHIVE**: unique, from a closed PR, or older than 11-01 and never in a PR. Expected: docs/gclive-2026-10-30, the
  origin/gc6/* branches, and origin/build/{255-never-split, 338-353-gate-fixes, 352-1-next-day, W-124-a3-chain,
  c4-row-31b, fix-381-257}. Action: run the content test first (technical call 4). If the content is superseded, the
  branch becomes CONTAINED. Otherwise tag it `archive/2026-11-07/<name>`, push the tag, then delete the branch.
- **STASH**: both stashes become tags `archive/2026-11-07/stash-<date>`, then `git stash drop`.
- The `-ic-audit-docs` tree: if any file under it changed in the last 2 h, or it has a lock, another session may be
  active. Wait up to 30 min, then log it and treat it as MERGE by sha (its commits are on the branch).

## §2 Integrate on feature/adjustments (settings tree)
1. `git merge origin/main`. Resolve conflicts with main's spec/ADR rows kept and the branch's code kept. Regenerate
   generated files with `regen.py` (never hand-merge `views/`, the findings index or `docs/api/openapi.json`).
2. Merge each MERGE branch by sha, one at a time. After each one, run that branch's changed files' tests.
3. Core proof: `python scripts/orchestrator/prepush.py --full` writes its PASS marker for HEAD, and `alembic heads`
   shows exactly one head. Record both in the log.
4. Push feature/adjustments to origin (the merge commits on top of the §0b push).

## §3 PR to main and review (Tier A)
1. `land.py <settings tree> --title "Land feature/adjustments on main (GC-ADJ1/2, GC-SET, GC-MU, GC-ALERT1, GC-IC1,
   fix batch 1)" --body-file <body> --reviewed-sha <HEAD>`. The body carries a Spec-deviation block (`Class: none`),
   "addresses #664" (never "fixes"), the manifest summary and the review tier.
2. Fresh Opus reviewer, read-only. `Why Opus:` 15 migrations + merge of 975 commits. `Budget: 40 min, 60 tool calls`.
   `Report: evidence-table`. Scope = technical call 5. CRITICAL/MAJOR findings get fixed in at most 2 rounds. A new
   push means re-review only for the touched files.
3. CI: `lint-and-test`, `coverage` and app-tests must be green. Red: `gh run view <id> --log-failed`, fix, push again.
4. `python scripts/orchestrator/merge.py <pr> --reviewed-sha <sha>` (merge commit). Prove the merge:
   `git merge-base --is-ancestor <feature/adjustments tip> origin/main`, and the tree of `origin/main` equals the tree
   of the PR head (or differs only by the merge-base refresh).

## §4 Cleanup (only after §3 is proven)
1. Fast-forward the main checkout to origin/main. Copy the GC-MERGE1 contract and the handovers onto main (they ride in
   with the merge).
2. Remove every worktree except the main checkout and `-live` with wt-rm.ps1, using `-MergedInto origin/main`. First
   unlock the 3 locked trees (`git worktree unlock`; they belong to finished sessions, see the sweep ages). Delete the
   untracked `npmci.log` in the cfg-source-chips tree (it is a log) before removal. Log the counts before and after
   each removal. Then `git worktree prune` and delete any empty folders left in `.claude/worktrees/`.
3. Delete local branches: CONTAINED (`git branch -d`, which refuses an unmerged branch; never `-D` unless the manifest
   row shows a pushed archive tag). Delete remote branches: `git push origin --delete <name>` for CONTAINED and
   ARCHIVE-tagged branches. Keep `main`.
4. Delete the stale lock `D:\Abhay\scratch\ic-e2e\.run-active.lock` (11-05; that session is over, so record it in the
   log).

## §5 Move the live app to the main checkout
Allowed outside 09:00-15:35 IST on weekdays, any time on a weekend. Steps: `pg_dump` ofo_dev to
`D:\Abhay\scratch\gc-merge1\ofo_dev-pre-merge.dump` → `dev_run.py . python -m alembic -c backend/ofo_app/alembic.ini
upgrade head` → stop the 8765 server by its port owner PID → start it from the main checkout the way the `-live` tree
ran it (read its start command or script first) → `GET /health` (or the app's status route) returns 200 and the
strategies page loads in the owner's Chrome → wt-rm the `-live` tree. If the health check fails: restart from `-live`
(still on disk), log it, park it, and leave `-live` in place.

## §6 Done means (each one is an evidence-table row with the command run this turn)
| Check | Command | Expected |
|---|---|---|
| Unpushed commits backed up (§0b) | `git rev-list --count origin/feature/adjustments..<0b HEAD>` (before branch deletion) | 0 |
| Branch landed | `git merge-base --is-ancestor <adj tip> origin/main` | exit 0 |
| Worktrees | `git worktree list` | 1 line (main checkout) |
| Local branches | `git branch` | `main` only |
| Remote branches | `git branch -r` | `origin/main` (+ HEAD) |
| Stashes | `git stash list` | empty |
| Nothing unique lost | for every manifest row: ancestor of origin/main OR archive tag on origin | 0 rows failing |
| Main checkout clean | `git status --porcelain` | empty |
| Live app | health route on 8765 | 200, served from the main checkout |
| Backup | `git bundle verify <bundle>` | OK |

## §7 Tracking and final report
- `manifest.csv` + `progress.md` in `D:\Abhay\scratch\gc-merge1\`. The final manifest is copied to
  `docs/process/branch-cleanup-2026-11-07.md` (table: branch → category → action → proof).
- Handover `docs/process/session-handover-2026-11-07-merge.md`: DONE / PENDING / BLOCKED / PARKED / NEXT, the archive
  tag list (for the owner to look at whenever they like), review verdict, CI run ids and merge sha. Both files go to
  main in ONE small docs PR (merged via merge.py), which runs before the final branch deletion of its own branch.
- Memory: replace the START HERE lines (fix batch 1, IC fix batches, adjustments-feature-branch) with one line saying
  main holds everything, and NEXT = the batch 2 contract, cut from main. Update `adjustments-feature-branch` so it says
  the branch is retired.

## Out of scope
New features, IC fix batches 2-6, the #664/#663 fixes, merging any closed-PR code, deploys, and the content of
`D:\Abhay\scratch` (only the stale lock is removed).

## Verification (how the run proves it)
§2.3 is the core proof (prepush --full PASS + one alembic head). §3.4 proves the merge by ancestry and tree equality.
§6 is the end-state table, run fresh in the final turn. The bundle plus the archive tags make every deletion
reversible: `git fetch <bundle> <ref>:<ref>` restores any branch.

Estimate (measured on past runs, not guessed): prepush --full ~25 min, CI ~30-40 min, review ~40 min, conflict fixes
0-2 h, cleanup ~45 min, live move ~20 min. Total about 3-5 h.

**Paste into a fresh session:** `/goal Run docs/process/goal-contract-GC-MERGE1-2026-11-07.md (settings tree, feature/adjustments) to its Done-means table.`

## Context (from the planning session)
Owner, 2026-11-07 ~19:30 IST: merge `feature/adjustments` and any other code lying around into `main`, clean every
worktree, leave nothing behind, with proper tracking, and only then start new work. Owner answers (question tool):
- **Q1 "Merge now, as is"**: this is the explicit approval for the merge to main that the 10-30 rule required. Batch 1 is
  closed. #664/#663 stay open as issues. IC fix batches 2-6 are NEW work after this, built on main.
- **Q2 "Triage: merge recent, archive closed"**: compare each other branch with main by content. Already there = delete.
  Unique, recent (after 11-01) and never in a PR = merge. From a closed PR (or older and never in a PR) = keep as an
  archive tag, do not merge, and list it in the report.

Measured state at 19:45 IST (Sat 2026-11-07):
- `feature/adjustments` (settings tree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-settings`, tip
  `ebefb113`) is 975 commits ahead of main and 3 behind. 82 of those commits are NOT on origin (laptop-only risk). The
  diff vs main touches 1,239 files and 15 alembic migrations.
- 22 worktrees: 19 agent trees under `.claude/worktrees/` (3 locked, 2 detached, 1 with only an untracked `npmci.log`),
  `-ic-audit-docs` (5 unique commits, today), `-live` (the owner's live dev app on 8765 / `ofo_dev`), and the settings tree.
- ~230 local branches and 40 remote branches. Every local branch except these is already contained in
  `feature/adjustments` or main: build/merge-preflight (5), docs/gclive-2026-10-30 (19), docs/ic-e2e-audit-2026-11-07
  (5), fix/cfg-source-chips (1). The fix/live-* and live/2026-10-30 branches have 0 commits that are not already present
  under another id. Remote-only unique branches: origin/gc6/* (8), origin/build/{255-never-split, 338-353-gate-fixes,
  352-1-next-day, W-124-a3-chain, c4-row-31b, fix-381-257}. All of those come from CLOSED PRs (10-20 to 10-26).
- 2 stashes (10-08, 10-24). 1 stale run lock `D:\Abhay\scratch\ic-e2e\.run-active.lock` (11-05). No open PRs.
- main is protected (required checks `lint-and-test`, `coverage`, strict, admins enforced) and uses merge commits
  (#611, #619-#621). A main push runs CI only and deploys nothing.

## Technical calls (mine, recorded in the contract; information, not questions)
1. **Back up first.** Make one `git bundle --all` file plus a manifest CSV before anything is deleted. Every deletion
   can then be undone from the bundle.
2. **Merge commit, never squash.** Then every branch sha becomes an ancestor of main, and "contained in main" stays a
   provable `git merge-base --is-ancestor` check during cleanup. A squash would make every branch look unmerged.
3. **The integration happens on `feature/adjustments` itself**, in the settings tree: merge origin/main in, then the
   recent-unique branches. Then one PR, feature/adjustments → main, via `land.py` + `merge.py --reviewed-sha`.
4. **"Superseded" is a content test, not a commit-id test.** `git cherry` plus a `git merge-tree` into the merged tip:
   if the result tree equals the tip's tree, the branch's content is already there.
5. **Review = Tier A** (15 migrations, ADR-189 alembic path): one fresh Opus reviewer, scoped to (a) the conflict
   resolutions, (b) a single alembic head + upgrade/downgrade on a throwaway DB, and (c) proof that main's 3 commits
   survive. The feature code was already reviewed piece by piece on the branch. Nobody re-reads 672k lines.
6. **Live app move.** After the merge the main checkout becomes the live app's folder. Outside 09:00-15:35 IST on
   weekdays (any time on a weekend): `pg_dump` ofo_dev → `alembic upgrade head` via `dev_run.py` (ofo_dev only,
   ADR-078) → restart 8765 from the main checkout → health check → remove `-live`.
7. **Archive tags** (`archive/2026-11-07/<branch>`) are pushed to origin only for unique, unmerged branches (~20).
   Contained branches are simply deleted, because main and the bundle both hold them.


## §1b Amendment 1 (owner, 2026-11-07 22:20-23:10 IST): audit the archived branches, keep parked work parked, record where it lives

Owner, verbatim, in order:
1. "update this goal contract accordingly so that all those 15 branches are also audited and their code checked, and
   wherever needed they should be merged to main."
2. "No new implementation, just merge all the code. Do not leave anything. For the parked items, keep them parked."
3. "find out and list what all things were parked and why they were parked and in which branch they are parked, so
   that in future whenever the implementation starts on those parked items, it should not begin from the beginning,
   it should begin from those parked branches."
4. "Update the goal contract with your recommended sequence."

This replaces the ARCHIVE line of §1 for the 15 branches.

1. **Audit (done 22:30-22:45).** Each of the 15 branches was checked against the integrated tip a4b9b339: verdicts in
   `docs/process/archived-branch-audit-2026-11-07.md`. Result: 14 are PRs parked together on 2026-10-29 under #605
   ("held for the live Kite gate"; order path out of scope per ADR-165); 1 (docs/gclive-2026-10-30) was never in a PR.
   No branch was superseded by a re-implementation; none is obsolete.
2. **Merge vs park (owner item 2).** The 14 #605 branches stay parked: not merged, kept as archive tags
   `archive/2026-11-07/<branch>`. docs/gclive-2026-10-30 is merged (its 2 docs files) in the GC-MERGE1 docs PR. The 2
   stashes hold 0 changed lines; tags kept, nothing to merge. No new implementation in this contract.
3. **Parked register (owner item 3).** `docs/process/parked-register-2026-11-07.md`: every parked item in the repo (44
   parked issues + the 14 #605 PRs = 57 rows): what, why (quoted), done/left, branch, and a PERMANENT resume ref (an
   archive tag or a commit in main's history; never a branch name, since branches are deleted in §4). Four parked heads
   that had no permanent ref were tagged 2026-11-07 (archive/2026-11-07/live/2026-10-30,
   build/W-024-error-catalogue-r3, build/W-021-reconciliation, build/W-023-partial-execution). Rule for future work:
   start a parked item with `git checkout -b <new> <resume ref>`, merge main in, run its own tests; never from scratch.
   #605 gets a comment linking the register and the 14 tags.
4. §6 gains a row: every register row has a resume ref that exists on origin (tag) or is an ancestor of origin/main.

## §8 Sequence after GC-MERGE1 (owner item 4; my recommendation, recorded)

1. **GC-MERGE1 first, nothing else (tonight).** Land #665, clean up (§4), move the live app (§5), one docs PR (audit,
   register, this amendment, docs/gclive files, handover). Why: every later contract is cut from main; starting before
   main is clean recreates two drifting code lines.
2. **IC fix batches 2-6 next, each absorbing its parked IC items.** The parked issues in the adjustment / iron condor
   feature the owner uses live (strategy 82): #664, #661, #662, #636, #638, #645, #624. Each batch contract lists its
   parked items with their resume refs from the register. Why: bugs in the feature in daily use cost the owner now.
3. **Builder-scope parked items, one batch.** #558 (row 31, REQ-085, with archive tag build/c4-row-31b), W-124
   (archive tag build/W-124-a3-chain; "much superseded by GC-UI, re-check first"), #596, #616, #433, #434, #560, #561.
4. **The 14 held PRs (#605) only when order placing comes back into scope.** That is an owner decision (it amends
   ADR-165). Then rebuild in #605's order (1 -> 14) from the archive tags, all of rows 1-12 before the first real order
   (example: without row 3 "never split", a Complete above the freeze limit is sliced on the guessed 1,755 units).
5. **Process/tooling parked items when convenient:** #200, #247, #517, #519.
6. Steps 2-3 need no new owner decision; step 4 needs the ADR-165 decision first.

## §1c Scope added during the run: the app DB test suite (2026-11-08 00:40-11:50 IST; technical, under the run's safe default "hold and fix")
§3.3 required app-tests green. The `api` job (the DB suite) could not finish on this branch; it had been date-red since
about 11-04 and was never run in full (the local gate skips DB tests). Four classes, each fixed at class level and each reviewed:
the fixture-date bomb (#649: one token per symbol + one union load, guards), shared state between test files (one
database per test file cloned from the migrated template), 9 stale expectations (each citing the migration/ADR that
changed it), and #663 (per-test strategy, ADR-245 fakes, cap tests on a T-01-only plan). Result: #665 merged with all 8
checks green (api 6126 tests). `domain-tests` became a required check on main. Details: #649 and #663 comments, and
`docs/process/session-handover-2026-11-07-merge.md`.
