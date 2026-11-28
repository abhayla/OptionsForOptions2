# Harvest issue (ready to file, not filed): lane rules for parallel cloud sessions

For the kit repository `abhayla/Startup-Factory`, label `harvest`. Not filed from this project: the owner or the
coordinator files it. Nothing in the kit repository was touched.

## Title

harvest: add a `lanes` skill and a three-line rule for parallel cloud sessions (coordinator and lanes)

## Why

OptionsForOptions2 ran several cloud sessions ("lanes") in parallel on 23 to 27 Nov 2026 under one coordinating
session. The same mistakes cost hours and money until the owner wrote the rules down:
- The coordinator built and tested code itself, so its context filled up and the lanes waited.
- Every session ran on its default top model, including mechanical work like regenerating files.
- An unrelated task was stacked on an old lane, whose long context made the answers worse.
- Two lanes edited one file, and two lanes each wrote the same decision number.
- The coordinator repeated a lane's report as fact without looking at the branch.
- Gates failed after a 35-minute run for reasons a 5-minute pre-check would have found.
- Owner questions were asked twice, mixed with other questions, or about technical choices.

Every project built on the kit that uses more than one session meets the same problems, so the rules belong in the
kit: a skill with the full text and a short always-loaded rule that points to it.

## Proposal 1: adopt this as the kit skill `.claude/skills/lanes/SKILL.md`

The text below is the project's skill, complete. Two project details to generalise on adoption: the decisions index
path (`docs/process/owner-decisions-by-subject-2026-11-26.md`) and the broker line (rule 10 of the brief template).

````markdown
---
name: lanes
description: How to run parallel work in cloud sessions ("lanes") with a coordinator, without two lanes doing the same thing or overwriting each other. Use when the words lane, parallel session, cloud session, child session, coordinator, orchestrate or fan out come up, before starting a lane, when writing a brief for one, when choosing a model for a task, when running a live test day, and when closing a lane.
---

# Lanes (parallel cloud sessions)

A lane is one cloud session with one goal, one branch and a fixed list of files it may edit. The coordinator is the
session that talks to the owner and runs the lanes. These rules come from the owner's instructions of 25 to 27 Nov
2026. Each line says what to do and why. Times are in the owner's time zone (IST).

## Roles
- The coordinator only asks, splits, routes, verifies and reports; it builds nothing, runs no tests and does no
  mechanical work itself (its context is the one thing every lane depends on).
- A lane does one goal on its own branch and reports in the fixed line below (so the coordinator reads one line, not a
  transcript).
- The owner answers business questions, types approvals, and archives finished lanes (only he can for a device-bound
  lane).
- Technical and architectural calls are the coordinator's, never the owner's (he decides what the product does).

## Starting a lane (the brief template)
Every brief is self-contained: the lane does not see the coordinator's conversation. Every brief carries, in order:
1. `Spec basis:` the sections and decisions the task rests on (the repo's hooks refuse work without it).
2. The exact task and the evidence that shows it is done (so "done" can be checked, not argued).
3. `Branch from:` the branch or commit to cut from, and `Push to:` the lane's own branch. Never main, never the test
   branch, no PR unless the owner asked (a stray push to a shared branch breaks other lanes).
4. `May edit:` the files the lane owns. `Do not edit:` the files other lanes own, with the lane names (see Files).
5. `Budget: <N> min wall-clock, <M> tool calls`; at budget the lane stops and reports done / not done / next command.
6. `Gate:` the exact commands to run before every push (see Reporting for the fast pre-check and the gate).
7. "Do not file GitHub issues: list them under To file as deferred issues" (the coordinator files them once, with no
   duplicates).
8. `Model:` and, for Opus, `Why Opus:` (see Models).
9. `Report:` the one-line report shape below.
10. Where the project has a broker: "paper only; never call a broker order endpoint" (a lane can lose real money).

## Models
- The task picks the model, never the session's default (the default is not chosen for the task).
- Haiku does mechanical work: regenerating files, reading logs, counting, applying a status line, merges and builds
  (cheap and fast, nothing to judge).
- Sonnet does building, test runs and browser walk-throughs (enough skill, and a fraction of the cost).
- Opus is used only for an independent (Tier A) review of a money, stop, exit or price path, or a live-database write,
  and the brief states `Why Opus:` (a wrong answer there costs real money and Opus is the scarce model).
- Never use the coordinator's own top model for code work (it is the model that must stay free to coordinate).
- Start a lane whose whole job is wording or documents on Sonnet (no judgement on money paths is needed).
- Start a lane that touches stops, exits, prices or money on Opus (a mistake there is expensive to find later).
- Each lane's results file carries a table `task | model that did it` (so the owner can check the routing).

## Context
- Give a finished lane a next task in the same session only when it is a related follow-up in the same code (it
  already knows that code).
- Send an unrelated task to a FRESH lane with a self-contained brief (old context makes answers worse and costs more).
- Never stack unrelated work on an old context.
- A finished lane reports `SAFE TO CLOSE (head <sha>, what is left)` and the owner archives it (archiving deletes the
  machine, so the push must be confirmed first).
- Queue each lane's next related task before it finishes, so no lane sits idle.
- Give every item an owner lane; an item without one is never started (it is found missing at the worst moment).
- Check every lane each time any lane or the test machine reports (one report often unblocks or invalidates another).

## Reporting
- Send one line per push to the coordinator: `head <sha> | gate <result> | re-test <what>` (the shortest message that
  lets the coordinator verify).
- A lane whose messages are refused writes the same lines at the top of its results file and pushes it early as a
  docs commit (the coordinator can still read it from the branch).
- The coordinator reads the branch, and never states a lane's status without having looked at its branch or session
  that minute (a stale status is worse than none).
- Verify before telling the owner: another session's report is a claim, so re-read the artifact first (branch head,
  log line, database row).
- Run the fast pre-check before every gate: `python -m pytest tests -m repo_scan -q`, then the runbook's list (a gate
  run is about 35 minutes; a failure found by the pre-check costs 5 minutes).
- Never bypass the gate (no `PREPUSH_GATE_ALLOW`); generated files are regenerated by the gate helper, never by hand
  (hand edits drift and fail the check).
- In cloud containers run Python gates with the proxy variables unset: `env -u HTTPS_PROXY -u HTTP_PROXY -u https_proxy
  -u http_proxy -u ALL_PROXY -u all_proxy` (the proxy breaks the local test servers).
- Write times in IST, in plain words, with the bad news first and no repeated messages (the owner reads on a phone).
- Never write a private link (status page, tracker) into a repository, commit, issue or PR (the repo is public).

## Files and branches
- Give each file one owner: every brief names the files the lane may edit and the files other lanes own (two lanes on
  one file overwrite each other).
- Never let two lanes edit the same file; a shared piece is built by one lane and adopted by the others (one
  version of the truth).
- Split by files, not by bug: two bugs in one file go to one lane.
- One branch per lane, cut from the same commit; merge, never rebase or force-push a branch another session uses.
- The coordinator hands out decision numbers; a lane never picks its own (two lanes once wrote the same number).

## Approvals and permissions
- Expect a lane's safety check to refuse edits to oversight files (gates, allow-lists, review notes, standing
  direction) unless the owner types the approval into that lane himself (the check is meant to stop silent changes).
- Bring the owner one paste block per lane, early, never after a failed gate (he can answer once, not after a lost
  35 minutes).
- After a worker restart, tell the owner to set Auto mode again (a restart can reset a session's permission mode).
- Do not try to archive or read the transcript of a device-bound lane: ask for SAFE TO CLOSE and the owner archives
  (the coordinator has no access to it).

## Questions to the owner
- Ask only business or functional questions, one at a time, alone in the message (mixed messages get half answers).
- Look the subject up in the decisions index first (`docs/process/owner-decisions-by-subject-2026-11-26.md`) and
  never ask the same subject twice (he has already answered most of them).
- Write the decision row the same turn an answer arrives (an answer with no row is lost at the next restart).
- When the owner is away or has given authority: decide the spec-conformant choice, record it with its reason, and list
  it for his review (waiting costs more than a reversible choice).
- Do not hold work for an answer: start what needs no answer (most work does not).

## A live test day
- Prepare before execution: the evening before, have the set-up (backup, migrations, restart), the final plan, the
  start message and the login steps ready (nothing should be built while the market is open).
- Run everything that needs no live market before the market opens (market hours are short and cannot be repeated).
- The test machine tests as a user in the browser, critical checks first (a late blocker is worse than a late cosmetic
  issue).
- Run two tracks when one track cannot finish the list (the day has a fixed end).
- Never wait on the market: set levels so they trigger (the price may never move to the level you wait for).
- Never skip a check because a helper's budget is low; give the helper more (a skipped check is an untested path).
- Send a status every 15 minutes in a short fixed shape: changed rows only, in complete sentences (so it can be read
  in 30 seconds).
- Refresh the status page every 15 minutes (it is what the owner opens first).
- Put every issue found on one list with criticality, dependency and owner lane (one list, no lost item).
- Collect usability notes separately and do not act on them that day (they pull attention from the critical checks).
- Fix a blocker at once on its own small branch cut from the tested head (it must not carry untested changes).
- Have a fix that touches money, stops, exits or prices reviewed, then gated (the cheapest place to catch it).
- Pull a fix into the test machine with a written PULL order: merge, build only if the frontend changed, restart only
  what changed, measure before and after, and the re-run list (so the test machine does not guess).
- Use one restart for several fixes where possible, and measure each fix (restarts cost test time; unmeasured fixes
  are unproven).

## Closing a lane
1. The lane pushes its last commit and its results file, with the `task | model that did it` table.
2. The lane reports `SAFE TO CLOSE (head <sha>, what is left)`; the coordinator re-reads the branch head on GitHub.
3. The coordinator files the lane's `To file as deferred issues` list once.
4. If a related follow-up exists in the same code, queue it in that session; otherwise start a fresh lane.
5. The owner archives the lane after the push is confirmed (archiving deletes the machine).
````

## Proposal 2: three-line always-loaded rule (fits the kit's budget of 5 rules and 8192 bytes)

File `.claude/rules/kit/lanes.md`, about 600 bytes:

```markdown
# Scope: global (this project)
- **L1 Coordinator and lanes.** The coordinator only asks, splits, routes, verifies and reports; every lane brief
  names its files, branch, budget, gate and model. Load skill `lanes` before starting a lane.
- **L2 Model and context.** The task picks the model, never the session's default (Haiku mechanical, Sonnet building
  and tests, Opus only for a money/stop/exit/price review with "Why Opus"); unrelated work goes to a fresh lane.
- **L3 Verify.** A lane's report is a claim: re-read the branch before telling the owner; ask the owner only
  business questions, one at a time.
```

If the kit's rule budget is already full, fold L1 to L3 into the existing run-discipline rule (it already has A1 to F1
on queues, briefs and budgets) and delete what that replaces.
