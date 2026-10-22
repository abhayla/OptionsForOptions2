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
