# Scope: global (this project)

# Run discipline: keep going, park what is stuck, stay lean

version: "2.0.0" (lean: OD-117)

- **A1 Run the queue to completion.** Stop only when the queue is empty, a genuine blocker is hit (owner-only
  credential, unavoidable spend, production deploy, irreversible op, true product fork) or the owner interrupts.
  For CI or a deploy window, work on something else. Counter: turns ending with queue items left.
- **B1 Park, don't drag.** At most 2 rounds per item; then park (open a `parked` issue with evidence and what is
  left) or ship with the findings listed for the owner. Before any new round on a parked branch, merge main into it,
  run the guard tests and record the merge commit in the parked issue. Counter: rounds per item.
- **B2 Owner away: never ask.** Decide a spec-conformant choice and record it; anything else goes to a dated
  owner-questions file with a recommendation.
- **B3 One session per goal,** with a DONE/PENDING/BLOCKED/PARKED/NEXT handover. An item with a parked remainder stays
  PARTIAL and names the issue.
- **C1 Run CI's own checks locally once per batch** before the first push (`python tools/ci_local.py`); generated
  files stay out of feature PRs. Counter: red CI runs per PR.
- **C2 Briefs carry the checklist:** exact assertions, fail-closed paths, every answer state (stated, absent, not
  found, failed, empty, ambiguous), and the `.claude/kit/builder-brief.md` standing items. Counter: findings in
  round 1.
- **C3 Prefer a structural guarantee** (the one code path every case passes, checked to run first) over another
  detector. Counter: detector patches per class.
- **C4 A defect outside the item's done list** becomes a `deferred` issue with evidence.
- **D1 Zero hits proves only the pattern failed;** search loosely, read the source. "It ran" is a check, never a
  proof: name the counter that moved. Chain a gate with `&&`, never `;`. Counter: claims backed by a named counter.
- **E1 Every brief carries `Budget: <N> min wall-clock, <M> tool calls`;** at budget stop and report done / not done /
  next command. Targeted tests, long output to a log file, only the tail read. Counter: briefs without Budget.
- **E2 Shared state records its owner;** no recurring timer in a long session; name the cause before re-running a
  hung command.
- **E3 At most 5 always-loaded rules, 8192 bytes total** (`budget.json`); delete what you deprecate. Counter: bytes.
- **F1 Worktrees:** create with a purpose and 48h TTL, remove when the use ends (links first, never through them),
  then count tracked files before and after. Counter: worktrees past TTL.
