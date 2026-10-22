# Per-row process review (builder sequence and every later delivery run)

Owner decisions 2026-10-22 (~12:10 IST, question tool, three answers): (1) learnings live in this project's process
files, and the parts every project should get go to the kit as a `harvest` issue; (2) the orchestrator writes the
review itself right after each row closes, from measured facts, with no extra agent; a fresh agent reviews the reviews
every 3rd row and at each chunk end; (3) a change that adds a check, sharpens a brief or cuts waste without dropping a
check is applied at once; a change that removes or loosens a check, a review round, a verifier or a safety rule first
gets an independent reviewer's read, then goes to the owner as one question. Every change is logged below with its
reason. Strict row order stays (owner, same session: "Keep strict order").

## The review (same turn the row closes, before the next row's build)

1. **Measure** from the dispatch notifications: for each agent (start check, measure, build, fix, verify) its minutes,
   tokens and tool calls; the number of rounds; the orchestrator's own work outside agents.
2. **Right / wrong:** what worked; every extra round or continuation with its ONE-sentence cause, sorted into: brief
   gap, sizing, builder self-check, verifier miss, environment, owner question.
3. **Change:** for each cause, the smallest process change that would have prevented it, and where it lands
   (`docs/process/builder-brief.md`, the goal contract, a verifier brief template, a script). Applied the same turn
   under rule (3) above; a loosening change goes to a reviewer and the owner instead.
4. **Log** it here (newest first), and show the owner three lines (right / wrong / changed) under the status table.
5. Every 3rd row and at each chunk end: a fresh agent reads this log and the row records and reports what the reviews
   missed (it does not re-verify product code).

## Standing rules learned (applied to every brief from row 3 on)

- **R1 Attack list before the build** (cause: row 2 brief gap). The start check (built rows) or the Measure step (rows
  to build) writes the list of attacks the final verifier will run; the list is copied into the builder brief under
  `Attack list:`; the builder runs each one before reporting. Example: "a heartbeat alone must not count as a price".
- **R2 Builder runs every changed test file in full** (cause: row 1 stale picker test, row 2 stale status test). Not a
  `-k` subset. DB-backed `tests_app` files run through the MAIN checkout's `scripts/orchestrator/db_run.py <worktree>
  ...` (the worktree has no `.env`); a skipped DB test counts as NOT run and is reported as such. Before reporting,
  grep every test tree for the old value or old answer of anything changed.
- **R3 Size by files touched** (cause: row 1 continuation dispatch, 23 min, 178k tokens). From Measure, count the
  files the fix must touch: <= 5 files S (30 min / 40 calls); 6-15 M (60 / 80); more, or backend + frontend, L (split
  backend then frontend). A class spread over ~20 files is never S.
- **R4 Never mutate in place** (row 1 builder edited files in place for mutation checks and restored them). Mutation
  copies live in the agent's scratch folder only.
- **R5 Fix rounds go to the same builder** (it keeps context; measured 190-210k tokens vs 130-160k for a fresh one,
  but no re-reading time). Kept; re-measure at the chunk-end meta review.

Rejected (rule (3), loosening), 2026-10-22: "the final verifier skips ACs the diff did not touch". Independent
reviewer (Sonnet, fresh context): saves ~1-2 min per verify round on Tier B rows only (Tier A rows stay full), while
both stale-test failures of rows 1-2 were exactly "untouched" ACs broken by a shared change; a safe version needs an
import-graph script that eats the saving. Final verifiers keep checking every in-scope AC. Kit harvest of the adopted
rules: abhayla/Startup-Factory#161.

## Log (newest first)

### Row 2 - REQ-015 Zerodha connection (closed 2026-10-22 ~12:15 IST)
- Measured: shared start check 11.6 min / 185k (rows 1-2); build 12.4 min / 161k; verify r1 6.3 min / 160k; fix
  6.4 min / 191k; verify r2 4.9 min / 140k; orchestrator: 2 live proofs (owner session), 1 test expectation, owner
  question (AC-3). Total ~42 min of agents, ~650k tokens (+ half the shared start check).
- Right: the live proof against the owner's session caught what unit tests could not (status Connected 70 s after the
  last screen closed); asking the owner AC-3 early removed a whole L-sized build (ADR-169).
- Wrong: round 1 failed because the brief said "a fresh frame within the window" without "a heartbeat is not a
  price" (brief gap -> R1); round 2 had one stale test the builder never saw because its DB tests skipped locally
  (builder self-check -> R2).
- Changed: R1, R2 added.

### Row 1 - REQ-001 Scope (closed 2026-10-22 ~11:35 IST)
- Measured: build 8.9 min / 133k (ran out of budget); continuation 22.8 min / 178k; verify r1 7.1 min / 154k; fix
  8.0 min / 210k; verify r2 5.1 min / 146k. Total ~52 min, ~820k tokens.
- Right: one structural home for the underlying set plus a scan test as second layer; the verifier's 25-shape probe
  found the scan's blind spots (deferred #512).
- Wrong: sized S with 40 calls for a class spread over ~20 files (sizing -> R3); a stale picker test left red (builder
  self-check -> R2); mutation checks done by editing real files (R4); the orchestrator's own W-129 `tests_required`
  entry named no file and turned a repo test red at row 2 (orchestrator self-check: run `tests/test_tests_required_exist.py`
  after editing any work item).
- Changed: R3, R4; orchestrator runs `tests/test_tests_required_exist.py` after every work-item edit.

### Step 0 (merged PR #511, 2026-10-22 10:33 IST)
- Measured: two parallel builders 6.0 min / 108k and 6.8 min / 83k; PR CI 7 checks green first time.
- Right: the core proof ran on replay AND live in one sitting; the owner's Kite login was used the same morning.
- Wrong: the kit guard blocks any shell command naming kit words (spec, tools, .claude, factory, views) including
  commit messages and `cd <dir> && python tools/...`; cost ~10 retries. Fix: run kit tools bare as
  `python tools/<x>.py <worktree-path>` from the main checkout, commit with `-F <message file>`.
