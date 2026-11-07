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
4. Push feature/adjustments to origin. That alone removes the laptop-only risk for the 82 commits.

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

