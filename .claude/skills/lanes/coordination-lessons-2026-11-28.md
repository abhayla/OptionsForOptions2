# Coordination lessons, 28 Nov 2026

Owner's order, 28 Nov about 18:40 IST: today's coordination lessons go into the lanes skill so they carry to future
sessions. Numbers are measured on 28 Nov unless marked E (estimate). The short list is in `SKILL.md`, section
"Coordinator: finish line, batches and waves". Why no new always-loaded rule: the always-loaded budget is 8192 bytes
(`.claude/kit/budget.json`) and the lanes skill is already read by every lane; the path-scoped rule
`.claude/rules/project/cloud-first-testing.md` already covers `.claude/skills/lanes/**`.

## 1. Finish line before fan-out
Class every open item MUST, SHOULD, LATER or OWNER, and write what closes it. Lead every report with burn-down: open,
proven since the last report, net. A new item is shown as "added", never folded into the total. Case: "passed in cloud"
stood at 123 for four runs (about 2.5 hours) while the list grew from 203 to 210. Reports said "all assigned, waiting 0"
and the work looked busy, but nothing new had been proven.

## 2. A lane closing is not work done
An ETA belongs to the work. A lane that finishes or hands over says nothing about the items it leaves. Count its
"Not done" and "For the owner lane" lists as open. Case: a lane's ETA was read as the ETA of its items, and the items
sat unowned. Hand-over gaps measured: 26 minutes and 7 minutes, median 16.

## 3. Batches
Per item: failing test, fix, targeted tests, one local commit. Two pushes per lane: batch 1 is the money-path items
(stop, exit, order, money), batch 2 is the rest. A full check at `--jobs 2` has a median of 23.6 minutes (range 22.9 to
27.1). About 30 percent fail once (E, 3 to 6 per source). Check minutes per item with 30 percent failures: 16.9 at 2
items per push, 11.2 at 3, 6.7 at 5, 4.2 at 8. One check covers every commit of the pushed head, because the marker is for
the pushed head. A code push has no cheap form, so there is no unchecked code push and no override.

## 4. Not one push at the very end
One push per lane looks cheapest (7 checks instead of 21) but costs more: money-path proof lands 03:20 instead of 01:45,
late merge conflicts were 5 in 8 merges (about 25 minutes each), and a lane that dies with a container loses all of it
(E: about 40 minutes per lane in expectation). Two pushes per lane keep most of the saving.

## 5. The build lane merges in waves
One combined check per wave of 4 to 6 heads replaces one check per branch. Measured: one branch per check cost 5.8
hours for 14 merges. Two waves and a final check are 3 checks (71 minutes) against 14 (330 minutes, E).

## 6. Check in the background; reviews alongside; the one code path
Run the check in the background and build the next item in a second worktree (never `--force` on removal). Run the
Opus review of the batch alongside the check, on money paths only, two rounds at most. Case: five reviews of the browser
lock each found one more hole. The fix that ended it was the one code path every case passes (the server key), not a
sixth patch to the page.

## 7. Split by files that do not overlap
Check the split against the tree before the briefs go out. Each shared file has a single owner named in every brief; the
others send the change to that owner. Case: one lane blocked at a merge conflict outside its own files and never pushed
again; the build lane met 6 document and script conflicts.

## 8. Signals
Lanes report by message at every push, when blocked and at 55 percent of context. Before a lane is called stalled, read
its last event or message. Case: a 24-minute check looked like a stall. An accepted build commit goes to the plan lane,
the PC and the test lane in the same step. Case: a plan lane sat idle 50 minutes waiting for a commit the coordinator
already had.

## 9. Device trust
Lanes could not message the coordinator until the owner approved device trust, once per session. After approval the
coordinator can no longer read lane events. Messages and origin are the only signals. Say so at session start so the
owner approves early and the coordinator does not plan around reading transcripts.

## 10. Quote facts from the source
A fact passed between lanes is copied from the source file with its path, never written from memory. Case: issue 876 was
passed as "14 triggers on"; the PC said 13 with two guards. Three lanes built the wrong shape.

## 11. CI and the age of main
CI runs only on pull requests and on main, so a lane branch with no pull request costs no CI. That is right for lane
branches and wrong for the build (lesson 13). Count the merge into main in the plan from the
start. Case: main was 11 days old, about 1,700 commits behind, so every selector diffed against that old main and every
check was judged on hundreds of files: about 15 minutes of waste per push (E; 1467 s for a 3-commit push against 470 s for
a small commit on a current main). A pull request of that size also will not fit one Tier A review.

## 12. One line per new lane
Tell the owner in one line what each new lane finishes that a running lane cannot. Lanes multiplied today while the
proven count stood still; the line forces the question "why not the lane that exists".

## 13. One draft pull request for the build, CI after every wave
Owner, 28 Nov about 20:00 IST, after the plan had dropped pull requests and CI altogether: "you almost removed CI and
PRs, which is not correct ... one lane can have one CI or PR after it completes all the work". The release manager's
counter-proposal was accepted with "Proceed with these three changes".
1. One draft pull request for the build branch into main (this weekend pull 881 for integration/weekend-r3-1129). It
   exists for CI only; never merged, never marked ready before the release decision.
2. CI runs on it after every merge wave. Lanes do not wait; it runs on the host's machines while they work. A red result
   goes to the lane that owns the failing file, as a money-path item if it touches one. Push once per wave, because a
   newer push cancels the older run.
3. A freeze needs a green CI run on the frozen commit, as well as the local check and the review, before a build is
   handed to a test round.
Unchanged: no pull request per lane; quick tests per item, two full local checks and two pushes per lane; the build lane
joins in waves with one combined local check each.
Why: the local check is run by the lane that wrote the code, on its own machine ("a student marking their own paper").
CI also runs what the local check does not: the Execute-screen click-through job and coverage. Twelve per-lane pull
requests would each be compared with an 11-day-old main and each cost a run of one to two hours, while saying nothing
about the joined build (5 of 8 joins had conflicts on 28 Nov). One run per wave checks the thing that will be traded on
and rehearses the merge into main.
Comparison of CI runs for the weekend: 0 (the plan before the owner's order), about 12 (one per lane), 4 (one per wave:
22:45, 01:45, 08:00 and the 10:00 freeze).
On a draft pull request the workflows behave so: `ci.yml` job `lint-and-test` is skipped (`if: github.event_name != 'pull_request' || github.event.pull_request.draft == false`; the local check covers it). `domain-tests.yml` (domain-tests) and `coverage.yml` (coverage) have no draft condition and run. `app-tests.yml` runs when the changed paths match its list, and then its `changes` job picks the jobs: api, frontend and execute-screen-e2e (the Execute-screen click-through) have no draft condition.
