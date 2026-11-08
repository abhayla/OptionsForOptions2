# Session handover: GC-MERGE1 (2026-11-07 19:52 to 2026-11-08 ~13:00 IST)

Contract: `docs/process/goal-contract-GC-MERGE1-2026-11-07.md`, with amendment 1 (§1b, §1c, §8) appended. Run log:
`D:\Abhay\scratch\gc-merge1\progress.md`.

## DONE
- **main holds everything.** PR #665 (feature/adjustments) was merged as `ef18093b`, with all 8 checks green: lint-and-test,
  coverage, domain-tests, api (6126 DB tests), frontend, execute-screen-e2e, changes, close-keywords. Proof:
  `git merge-base --is-ancestor f8f911bd origin/main` exits 0, and `tree(origin/main) == tree(f8f911bd)`.
- It brought in GC-ADJ1/2, GC-SET, GC-MU, GC-ALERT1, GC-IC1, fix batch 1, build/merge-preflight, fix/cfg-source-chips,
  docs/ic-e2e-audit, plus these repairs:
  - the 9 checks broken by fix batch 1 (pricing through the engine, ADR-008);
  - the kit CI 10-min cap, handled by a project `domain-tests` job; kit harvest issue abhayla/Startup-Factory#194;
  - 15 stale e2e specs and 2 screens that scrolled sideways at 390 px;
  - the DB suite (§1c): #649 fixture dates, one database per test file, 9 stale expectations, #663 isolation.
- **Reviews:** Tier A on a68dfce7 PASS (1 MINOR). An independent review of the date-fix approach changed the fix (REVISE). Tier A
  re-review of a68dfce7..90677e73: safety PASS (13 hostile database names refused by the drop tool); its MAJOR was the 14
  worker tests, since fixed. A throwaway DB downgrade to 0030 and back passed.
- **main protection:** required checks are now lint-and-test, coverage, domain-tests.
- **Cleanup:**
  - 25 worktrees removed with wt-rm. Every removal kept the main checkout at 4102 tracked files and 202 node_modules,
    before equal to after.
  - 387 local branches and 44 remote branches deleted.
  - 2 stashes dropped.
  - Stale lock `ic-e2e/.run-active.lock` (11-05) removed.
  - 148 loose builder logs moved to `D:\Abhay\scratch\gc-merge1\old-worktree-files`.
  - `docs/process/branch-cleanup-2026-11-07.md`: 445 rows, 0 without a proof (ancestor of origin/main, or an archive
    tag on origin).
- **Archive tags on origin:** `archive/2026-11-07/*` (21) and `archive/2026-11-08/*` (7), with the old 2026-10-29 tags
  alongside. Every unmerged branch and stash has one. Bundle: `D:\Abhay\scratch\gc-merge1\all-refs-2026-11-07.bundle`.
- **Owner decisions:** the 14 #605 branches stay parked; docs/gclive is merged in this PR; no new implementation. Parked
  register: `docs/process/parked-register-2026-11-07.md` (57 rows, every row has a permanent resume ref). Audit:
  `docs/process/archived-branch-audit-2026-11-07.md`. Sequence: contract §8.
- **Live app moved to the main checkout** (Sunday, so outside market hours):
  - Order of start: price feed `ofo_app.liveprices`, API 8765 (`FEED_MODE=bus`, `REDIS_URL=redis://127.0.0.1:6380/0`,
    `LIVE_MARKET=1`, `DB_POOL_SIZE=4`), background `ofo_app.background`, vite 5173 (`OFO_API_TARGET=http://127.0.0.1:8765`).
    All run through `scripts/orchestrator/dev_run.py D:\Abhay\Ventures\OptionsForOptions2`, started under Desktop Commander.
  - ofo_dev went 0044 -> 0045 after a logical backup: 44 tables, 41,330 rows in `D:\Abhay\scratch\gc-merge1\ofo_dev-pre-merge`.
    There is no pg_dump on this PC.
  - `/health` returns 200 with the database connected. Live Strategies lists the ofo_dev strategies.

## PENDING
- Throwaway test databases on the shared PostgreSQL that are under 24 h old, so `--sweep` keeps them:
  `ofo_test_tmp_20261108010340_5e12`, `_011228_e0b1`, `_012129_85bf`, `_031216_1453`, `_20261107211534_6a9c`. Run
  `python scripts/orchestrator/db_run_fresh.py --sweep` after 2026-11-09 ~04:00 IST.
- Stale vite 5174 was stopped; it pointed at the scenario copy 8766, which was already stopped. Restart the scenario copy with
  `D:\Abhay\scratch\ic-uitest\restart_scn.ps1` when needed.
- API log line "catalogue refresh refused" at the 11-08 restart (Sunday, no Kite session): not analysed.

## BLOCKED
- Nothing.

## PARKED
- The 14 #605 order-path branches (archive tags), and every row of the parked register.

## NEXT
1. IC fix batch 2, cut from main, taking in its parked IC items (#664, #661, #662, #636, #638, #645, #624) from their resume
   refs (contract §8 step 2).
2. Deferred test findings in the issue filed with this PR.
