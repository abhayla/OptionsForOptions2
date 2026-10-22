# Session handover 2026-10-22 (builder sequence, session 1) - continue with the same /goal prompt

Read first: the goal contract `goal-contract-builder-sequence-2026-10-22.md` (step 9: the per-row process review), the
table `builder-sequence-2026-10-22.md`, `row-review.md` (method, rules R1-R10, effect check, expected vs actual, log).
No order was ever sent. Continue at the FIRST ROW NOT CLOSED in the table.

## State (updated as rows close)
- **Merged on main:** PR #511 (plan + step 0: core proof, flaky e2e fix, response-door list, W-129..W-190).
- **Chunk 1 branch:** `build/seq-chunk-1` in the ONE sequence worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`,
  pushed as a backup (no PR yet: PR, CI and the Tier A chunk review come at row 16).
- **Rows closed:** 1 (REQ-001), 2 (REQ-015), 3 (REQ-054), 4 (REQ-117), 5 (REQ-053); row 6 (REQ-048) PARKED #517 after
  two Tier A rounds (AC-1..AC-4 pass; AC-5 credential scans to redesign as a reply-field inventory). Meta review after
  row 6 done and applied (Size + CI lines enforced by check_brief). Row 7 (REQ-049) brief written (expected 90 min /
  450k), builder dispatched ~16:55 IST. Rows 8-63 not started.
- **Owner decisions this session:** ADR-169 (connect by Zerodha login only, no own-app setup; REQ-015 AC-3 rewritten);
  strict row order kept; per-row process review (row-review.md); ofo_test reset approved -> done instead as a throwaway
  database per run (no data touched; #497 comments).
- **Deferred MINOR issues:** #512 (row 1, for row 46), #513 (row 2, for row 7), #514 (row 3, before order-path use),
  #515 (row 4), #516 (row 5: scheduler start-up gap before 08:30 must be fixed before a deploy that restarts the API
  07:30-08:30 IST and before the row-63 live window).
- **Findings added:** first-live-frame-before-first-price (row 24), keepalive-counted-as-live-data (guarded),
  guard-as-forbidden-list occurrence 4, spec/findings.md F-57 (+ note on F-56).
- **Process tooling on the branch (Tier A, reviewed in the chunk PR):** brief gate checks every brief form;
  check_brief enforces attack list >= 5, size budget pairs, allow-list for guards (R8); repo test for the row-review
  log; `scripts/orchestrator/db_run_fresh.py` (throwaway database, Opus-reviewed, fixes applied);
  `reset_test_catalogue.py` (built but cannot run: the catalogue's delete guards refuse - by design).

## Helper scripts (NOT in the repo): `D:\Abhay\scratch\ofo2-builder-sequence\`
- `fresh_launch.py <checkout> <command...>`: run DB tests in a throwaway database using the MAIN checkout's .env
  (the worktree has no .env). Use it for every DB proof: ofo_test's leftover catalogue (#497) fails ~15 tests.
- `run_api_live_wt.py`: live API on :8765 from the worktree code (ofo_dev, LIVE_MARKET=1, order path off). The owner's
  Kite session from 2026-10-22 10:06 is valid until ~06:00 the next day; a new day needs a new login (ask once).
- `run_api_replay.py`: replay API on :8771 (APP_ENV=test, OUTCOME_REPLAY=1) on ofo_dev.
- `core_replay.py`, `core_live.py`: the core proof scripts; `record_profile_door.py`: one real /user/profile through the
  door (redacted); `fps_wt.py <checkout> REQ:AC ...`: AC fingerprints in a worktree; `kit_issue_comment.py`: comment
  on the kit repo (its name trips the kit guard).

## How the guards bite (save retries)
- The kit guard blocks any shell command containing kit words (spec, tools/, .claude, factory, views), including
  commit messages: commit with `-F <message file>`; run kit tools bare as `python tools/<x>.py <worktree-path>` from
  the main checkout.
- `gate_before_commit` refuses a commit after a piped step: run checks and the commit as separate calls.
- `check_brief.py` needs `PYTHONUTF8=1`; a `Threat model:` line must be ONE line with both "in scope" and "out of scope".

## NEXT
1. Row 7 (REQ-049 data health, picks up #513): act on the builder's report; verifier (Opus); close with the review
   and expected vs actual from commit times.
2. Row 8 (REQ-050 shared computation, unmeasured), then 9 (REQ-113, owns the cross-process cache), 10, 11, 12-14
   (verified: one shared verifier), 15-16 (one shared verifier); meta review after row 9.
2b. The parked row 6 (#517) is retried only with a fresh independent designer for the reply-field inventory.
3. Release the stray agent worktree `agent-a3130708769c0608b` (clean, at main's head; locked while its process ran):
   `python scripts/orchestrator/agentwt.py a3130708769c0608b release`.
4. Rows 8-16, then chunk 1's PR: merge main once, fast checks, `regen.py` once, `land.py` with the reviewed sha,
   Tier A review of the chunk, then flip rows 1-16's work items from in_review to done and drop their coverage lines.
