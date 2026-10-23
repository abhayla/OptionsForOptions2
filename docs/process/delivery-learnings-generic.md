# Delivery-loop learnings (generic, for the Startup-Factory kit)

Written for any project built with the Startup-Factory kit (builder agent -> independent verifier -> evidence -> PR).
Project-specific detail stays in the project's own review log; this file keeps only what every project can apply.
Kept current at every meta review (every 3rd delivered item); the kit harvest issue links here
(abhayla/Startup-Factory#161). Source project: OptionsForOptions2, builder sequence, measured from 2026-10-22.

## What the cost actually is

- Every agent dispatch costs roughly 130-210k tokens and 5-23 minutes, almost independent of the task's size, because
  each one re-reads the spec and the code first. The lever is FEWER DISPATCHES PER ITEM, not faster agents.
- A resumed agent re-sends its whole history: a 4-tool-call follow-up to a resumed builder cost 203k tokens.
- Measured on the first three items: 52 / 42 / 37 minutes, ~820k / ~650k / ~650k tokens, 2 / 2 / 1 verify rounds.
  Every extra round had a preventable cause.

## Rules (each: the waste it removes, the evidence, how a project checks it)

1. **Attack list before the build.** The start check (item already built) or the measure step (item to build)
   writes at least 5 numbered attacks the final verifier will run, each naming the test file that should hold it;
   they go into the builder brief; the builder runs each before reporting. Waste: a verify round failing on an attack
   nobody wrote down (a liveness fix counted 1-byte keep-alive heartbeats as live data, so the status said "Connected"
   forever; the brief said "fresh frame within the window" but never "a heartbeat is not a data frame").
   Check: the brief checker refuses a builder brief with fewer than 5 numbered attacks.
2. **Builder runs every changed test file in full.** Never a `-k` subset; a test skipped for a missing database or
   environment counts as NOT run and is reported as skipped; grep every test tree for the old value or answer and
   report the grep and its hit count. Waste: stale assertions reaching the verifier because DB tests skipped silently.
3. **Size by files touched, not by how small the change sounds.** <= 5 files S (30 min / 40 calls), 6-15 M
   (60 / 80), more or backend + frontend L (split, each part 60 / 80). Waste: a "small" fix spread over ~20 files ran
   out of budget and needed a continuation dispatch. Check: the brief checker refuses a budget that is not a size pair.
4. **Mutation checks in scratch copies only.** Never edit a checked-out file to prove a test dies. Waste and risk:
   in-place edits in a shared worktree.
5. **Resume an agent only for a real fix round.** A follow-up of <= 3 files and no new design goes to a fresh agent
   with a narrow brief.
6. **The orchestrator checks its own bookkeeping.** After any work-item or stage edit, run the project's
   "every listed test file exists" and coverage checks. Waste: the orchestrator's own entry turning a repo test red.
7. **Measure every item.** Every agent's minutes, tokens and tool calls from its completion notice, times read from
   the clock or the commit, never typed. A review claim without a record is a defect (one close time was typed 40
   minutes off).
8. **Per-item process review, applied the same turn.** The orchestrator writes it (no extra agent); a fresh agent
   reviews the reviews every 3rd item; a repo test fails when a closed item has no review entry or a due meta review
   is missing. Changes that add a check apply at once; a change that removes or loosens a check needs an independent
   reviewer's read and the owner's yes.
9. **Effect check.** Each rule names the waste it targets and the counter that shows whether it came back; a rule
   whose waste recurs twice is rewritten or turned into a machine check.

10. **Prose rules break within one item; put them in the brief checker** (meta review after item 6: the budget hard
    stop, the size rule and the allow-list rule were each broken right after being written). The checker requires a
    `Size: S|M|L, <n> files, <k> items[, backend + frontend]` line whose budget matches (more than 5 files, more than 4
    items or both layers is never small), and a `CI:` line naming the job and variables that run each new test.
11. **A test must be run with exactly CI's variables, and must say which CI job runs it.** Waste: a test passed only
    because the builder's shell had a database variable CI does not set; a scan "ran" locally but no CI job both
    built the frontend and ran it; a fail-closed switch keyed on `CI` (set on every runner) turned an unrelated job red
    on every run.
12. **Guard secrets by inventory, not by names.** A checked-in list of every reply field (and every build-time
    variable), asserted both ways, so a new field needs review; never a list of secret-looking words (`token` or
    `kite_session` slipped through two rounds of name lists). The word "allow-list" in a brief is not an allow-list
    design: review the design.
13. **A run on shared test data proves nothing about the code.** Give each local DB run a throwaway database (create,
    migrate, run as the limited role, drop only what this run created); measured: 15 "known failures" + 5 unrunnable
    tests became 137 passing, with no shared data touched.

## Added after the third meta review (items 7-9 of the source project)

- **Builders do not finish their own proof steps; a script must.** In one large item, 3 of 4 parts needed a follow-up
  dispatch only to finish tests the builder had left (mutants never run, mutation output lost when a run was killed,
  guards with no killing test): 23% of the item's tokens. Fix: a mutation gate script the builder MUST run before
  reporting - it applies each mutant from the brief's attack list in a scratch copy, runs the named killing test,
  appends each result to a file as it finishes, and exits non-zero on any survivor or missing line; the orchestrator
  re-runs it as the gate. Measure: follow-up dispatches per item for builder-unfinished tests (target <= 1).
- **Write every mutation result to a file as it finishes.** Results held only in an agent's memory are lost when a
  run is stopped; a finisher then repeats the whole sweep.
- **A blocking question box at night idles the whole session.** A question asked late held a session ~7.5 hours for an
  answer the build did not need. Rule: use the interactive question only while the owner is active; otherwise write
  it to a dated questions file and keep building. Better by machine: a hook that refuses the question tool in the
  owner's night hours (fail open, override with a reason).
- **Cache keys built by hand drift from the computation.** 30 of 40 key parts of a shared-computation cache had no
  killing test. Build each key from the exact arguments of the call it guards, and test "change one input at a time
  -> recompute".
- **Building one item ahead, safely.** Owner-approved variant: the next item may be built while the current one is
  verified, items still close in order; the two never share a file, at most one database run at a time with the older
  item first, a separate worktree for the item ahead (its brief checked to name only that worktree, else its tests run
  the older item's code - a false green), and a rebase plus full affected-test run before its verifier.
- **Every timestamp in a review comes from a commit or the clock,** never typed: three of this project's reviews put a
  close time 4-16 minutes off.

## Rejected, with the reason (so other projects do not re-try them blind)

- **"The final verifier only checks what the start check asked."** Both first-round failures in the source project
  were defects the build itself introduced (a stale test, a new liveness bug); no pre-written list can name those.
- **"Skip re-checking acceptance criteria the diff did not touch."** Independent review: saves 1-2 minutes per round
  on low-risk items only, while the two stale-test failures were exactly "untouched" criteria broken by a shared
  change; a safe version needs an import-graph script that eats the saving.

## Guards a kit can ship

- A PreToolUse gate that runs the brief checker on the designated brief of every builder dispatch (match every
  prefix form the orchestrator uses, any folder under the process docs, both slash styles; fail open on a crash).
- A brief checker rule set: attack list >= 5, budget is a size pair, guard-test line present.
- A repo test: every closed item has a review entry; every 3rd has a meta review.
