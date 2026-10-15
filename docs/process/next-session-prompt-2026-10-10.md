# Next-session prompt (written 2026-10-10 ~07:40 IST by the previous session, which ran out of context)

You are continuing OptionsForOptions2 in `C:\Abhay\Ventures\OptionsForOptions2` on the **Windows VPS**. The owner is
present and follows this session from the Claude mobile app (Remote Control). Work rules as before: decide by role and
keep going; owner items only for approvals, credentials, spend and deploys; ask the owner ONE question at a time with
the question tool (recommended option first, `Spec basis:` inside); merge main into every branch and re-run the
checks before merging; evidence table for every done-claim.

## Read first, in this order
1. `docs/process/session-handover-2026-10-10.md` - what merged, what is parked, NEXT, the traps.
2. `docs/process/owner-questions-2026-10-10.md` - the open owner decisions.
3. `CLAUDE.md` and `docs/HANDOVER.md` (pointer at the top).
4. Your memory file `this-pc-is-prod-db-host` - this PC's PostgreSQL also serves IPODhan PRODUCTION: targeted test files
   only, every brief (builders, reviewers, verifiers) carries a load cap (probes < 30 s); full suites, Playwright, the
   frontend build and scale tests run only in CI. Use `python scripts/orchestrator/atool.py <worktree> <word> --no-tests`
   as the local CI mirror (it now runs every ci.yml lint step, the repo-wide guard tests, the coverage check and, when
   a branch changes a migration, every migration test through `db_run.py`).

## State at hand-over (main at the merge of `docs/leg-picker-ac`)
- Merged and verified this session: W-061 (Save Draft), #163, W-067 (history in PostgreSQL, ofo_test at
  `0010_strategy_schema_version`), #179, #174, #138/#167 (W-061 follow-ups), #184, #156, ADR-070 (repo public),
  findings and tooling.
- **PARKED:** W-066 (#172, draft PR #170, worktree `C:\Abhay\Ventures\OptionsForOptions2-W-066`); #155 hook (worktree
  `...-155`, branch `fix/155-gate-before-commit`, owner question 6).
- **W-065** live push: built, worktree `...-W-065`, branch `build/W-065-live-push`; needs the owner's Kite login during
  market hours - **today is Saturday 2026-10-10, market closed; a Kite session expires 06:00 IST next day, so the login
  and the live proof are for Monday 2026-10-12 after 09:15 IST.** Merge main into that branch first (main moved a lot).
- #148: design ready in `docs/process/design-148-response-door.md` (no code yet); waits on owner questions 7 and 8.

## Owner questions - status
- Q1 Kite login: Monday after 09:15 IST (owner confirmed Saturday is closed).
- **Q2 leg picker: ANSWERED 2026-10-10 - "New REQ-035 criterion".** Written into the spec as REQ-035 AC-8 (+ owner
  decision note, ADR-068 pin). Next: a work item for the leg picker under REQ-035 AC-8 (check the legacy-reuse map
  first, ADR-047; prove the core first).
- Still to ask the owner, ONE at a time, starting immediately: Q6 (#155: merge the partial hook now - recommended - or
  one more round), Q7 (#148: serve /docs and /openapi.json only in development/test - recommended), Q8 (#148 MAJOR 2 as
  its own round - recommended), Q4 (W-066 resume timing), Q5 (stale production-gate markers - only the owner can clear
  them; describe, never path, the seatbelt), Q3 (templates to read - ask whether a reading page would help).
  Write every answer back into the spec or the owner-questions file the same turn (spec-first rule R4).

## First actions
1. Read the files above (do not redo the work they describe).
2. Ask the owner Q6 now with the question tool.
3. Then work the queue: leg-picker work item (REQ-035 AC-8), #148 per the answers, the remaining owner questions.
