# Scope: global (this project)

# Run discipline: keep going, park what is stuck, cut friction, stay lean

version: "1.0.0" (generalized for the project kit)

Why: long runs stalled on status reports, dragged stuck items round after round, spent more on friction than code.

## A. Keep going

- **A1 Run the queue to completion.** A turn ends only when the queue is empty, a genuine blocker is hit, or the
  owner interrupts; reporting what landed is right, reporting and STOPPING is the defect.
- **A2 Genuine blockers only:** an owner-only credential, unavoidable spend, a production deploy, a
  destructive/irreversible op, a true product fork. NOT blockers: green CI, a rebase, a merge conflict,
  filing/closing an issue, writing a brief, dispatching a builder, the next approved item.
- **A3 Wait without idling:** for a real wait (CI run, deploy window), set a watcher and work on something else;
  state remaining items as in progress, never as a question back to the owner.

## B. Park, don't drag

- **B1 Park rule:** PARKED after two failed fix rounds, a 2-working-day-overdue real-world proof, or an outside
  blocker — open a `parked` issue with the evidence and what's left, note the tracker, move on; never retry silently.
- **B2 Owner away: never ask, park the question.** No interactive questions while nobody is watching; decide and
  record a spec-conformant choice like an owner answer; anything else goes to a dated owner-questions file with a
  recommendation, and the run continues.
- **B3 One session per goal**, with a DONE/PENDING/BLOCKED/PARKED/NEXT handover before another takes over.
- **B4 Honest verdicts:** an item whose remainder is parked stays PARTIAL and names the issue.

## C. Cut friction

- **C1 Measure before speeding up:** classify timestamped run events and CI history first.
- **C2 Generated files stay out of feature PRs**; indexes/boards/aggregates regenerate in one batched PR.
- **C3 Run CI's own checks locally before every push**, one command mirroring the PR gate.
- **C4 The reviewer's checklist goes into the builder's brief** (exact assertions, fail-closed paths, mutation tests
  first); depth follows blast radius, at most 2 rounds, then B1.
- **C5 Batch docs PRs:** findings, decision rows, ledger lines in one PR per batch.
- **C6 Prove right after merging**, on staging, triggering event proofs by hand instead of waiting.
- **C7 Timebox discovery:** a defect found OUTSIDE an item's done list becomes a `deferred` issue with evidence.

## D. Verification habits

- **D1 Zero hits proves only the pattern failed;** search loosely (quotes, case, plurals), then read the source.
- **D2 A missing log line is not a missing event;** find the emitting condition first.
- **D3 "It ran"/"0 stored" is a check, never a proof;** name the counter that moved, with identities.
- **D4 Chain a gate with `&&`, never `;`,** so a refused gate stops the merge.

## E. Tooling, shared state, context budget

- **E1 Project hooks live in this repo**, wired+tested in CI; a hook no-ops when its script is missing, and a
  presence check names any wired hook whose file is gone.
- **E2 Shared state records its owner** (marker/lock/queue names the writing session); only it acts/clears.
- **E3 No recurring timer in a long session** (each tick re-sends the whole context); watch from a small process.
- **E4 Lean briefs:** every brief carries `Budget: <N> min wall-clock, <M> tool calls`; at budget the worker stops,
  reports done/not done/next command; targeted tests not the full suite; long output to a log file, tail only.
- **E5 No dead text:** at most 5 always-loaded rules, rest path-scoped; delete what you deprecate; CLAUDE.md holds
  rules and pointers, not history.
- **E6 Never repeat blindly:** name the cause before re-running a hung command; polling twice is a loop, diagnose.

## F. Worktree lifecycle

- **F1 Create with a purpose:** `git worktree add` named `<repo>-<task>`, purpose/branch/TTL (default 48h) recorded
  in the handover or tracker.
- **F2 Remove when the use ends** (merged, PR pushed, or abandoned), same session; nothing outlives its TTL unnamed.
- **F3 Remove safely:** refuse an unmerged/unpushed tree unless discarding on purpose; delete junctions/symlinks as
  LINKS first, never through them (a forced delete following a link wipes the main checkout); then
  `git worktree remove` + `prune`.
- **F4 Prove the main checkout survived:** count tracked files AND dependency packages before/after removal; a
  mismatch stops the line (tracked files can stay equal while dependencies are emptied).

## CRITICAL RULES

- MUST follow A (keep working to an empty queue or a genuine blocker; never stop just to report status).
- MUST follow B (park after two failed rounds or a 2-working-day-missing event, with an issue; never ask while away).
- MUST follow C-D (local checks before push, batched docs PRs, generated files out of PRs; "ran"/"0 stored"/zero
  hits/a missing log line/a peer report are checks, never proof; chain gates with `&&`).
- MUST follow E (shared state's owner recorded, no recurring timer in a long session, `Budget:` + targeted tests in
  every brief, logs to files, at most 5 always-loaded rules).
- MUST follow F (worktree created with a purpose+TTL, removed the session its use ends, never through a link, main
  checkout's files+dependencies proven intact after).
