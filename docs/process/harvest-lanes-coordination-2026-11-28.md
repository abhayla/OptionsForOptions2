# Harvest proposal: coordinating many parallel lanes (for the Startup-Factory kit)

This is a `harvest` proposal text for abhayla/Startup-Factory. It is stored here because the session that wrote it
could not file an issue in that repository. File it there as is.

Source: one day (28 Nov 2026) of running about ten parallel cloud sessions ("lanes") under one coordinator. Numbers are
measured that day unless marked E (estimate). Proposed home: the kit's lanes or orchestration skill.

1. **Finish line before fan-out.** Class every open item MUST, SHOULD, LATER or OWNER with what closes it. Lead every
   report with burn-down: open, proven since the last report, net, new items as "added". Case: the proven count stood at
   123 for four runs while the list grew from 203 to 210, and reports said nothing was waiting.
2. **A lane closing is not work done.** An ETA is for the work. Count a lane's hand-over list as open.
3. **Batches.** Targeted tests and a local commit per item; two pushes per lane, risky-path items first. A full check
   took a median 23.6 minutes and about 30 percent failed once. Cost per item: 16.9 check-minutes at 2 items per push,
   6.7 at 5. One check covers all commits of the pushed head. Never an unchecked code push.
4. **Not one push at the very end.** Proof of the risky items lands about 1.5 hours later, late conflicts were 5 in 8
   merges, and a dead container loses unpushed work.
5. **Merge in waves.** One combined check per wave of 4 to 6 branches. One check per branch cost 5.8 hours for 14 merges.
6. **Check in the background, review alongside.** Build the next item in a second worktree while the check runs. Review
   only risky paths, two rounds. When several reviews each find one more hole, move the guarantee to the one code path
   every case passes instead of another patch (five reviews of one lock).
7. **Split by files that do not overlap,** checked against the tree. Name each shared file's single owner in every brief.
8. **Signals.** Lanes message the coordinator at every push, when blocked and at 55 percent of context. Read a lane's
   last event or message before calling it stalled (a 24-minute check looked like a stall). Send an accepted build
   commit to every waiting lane in the same step (one lane idled 50 minutes).
9. **Device trust.** Lanes could not message the coordinator until the owner approved trust per session; afterwards the
   coordinator could not read lane events. Messages and the remote branch are the only signals. Say so at session start.
10. **Quote facts from the source file,** never from memory, when passing them between lanes (a count passed as 14 was
    13 with two guards in the source; three lanes built the wrong shape).
11. **Lane branches have no pull request and no CI** (CI runs only on pull requests and the main branch); the build
    branch is the exception, see 13. Count the merge into main in the
    plan from the start. A main that is 11 days and about 1,700 commits behind made every check judge hundreds of files:
    about 15 minutes of waste per push (E).
12. **One line per new lane to the owner:** what it finishes that a running lane cannot.
13. **One draft pull request for the build, CI after every wave.** (a) One draft pull request for the build branch into
    the main branch, for CI only, never merged and never marked ready before the release decision; none per lane.
    (b) CI runs on it after every merge wave; lanes do not wait; a red result goes to the lane that owns the failing
    file; push once per wave, because a newer push cancels the older run. (c) A freeze needs a green CI run on the
    frozen commit, as well as the local check and the review, before a build goes to a test round. Why: the local check
    is run by the lane that wrote the code; CI also runs what it does not (a browser click-through and coverage); twelve
    per-lane pull requests would each be compared with an old main and say nothing about the joined build (5 of 8 joins
    had conflicts); one run per wave checks what will be traded on and rehearses the merge. Runs for the weekend: 0
    (no CI), about 12 (per lane), 4 (per wave). Note for your own workflows: a job guarded by "not a draft" is skipped on
    a draft pull request; check which jobs carry that guard.

14. **A message reaches a lane only when its current turn ends.** A lane in a long autonomous turn was deaf for four
    hours; "delivered" means queued, and a priority flag did not interrupt. An instruction counts only once the lane's
    next line acknowledges it. Place every hold at the build lane.
15. **Before a wave, list every lane's new migration.** Three lanes used the same number on one parent; two make two
    heads and the upgrade fails. The build lane chains them and the lanes adopt its numbering.
16. **A speed proof in a fast environment needs the real link's per-query delay.** A report ran in 0.2 s in the cloud and
    16 to 19 s on the real link (88 queries at 134 ms). Pin the query count, not the statement text.
17. **Run the whole browser suite before a wave.** It had grown from 282 to 1,956 tests with 75 failing and nobody had
    run it whole. CI's server job takes 80 minutes and a newer push cancels a run, so the last code wave is set by CI
    time, not by the freeze time.
18. **Two proof columns:** "walked on a lane branch" and "proven on the build" (walked on the build commit plus green CI
    on that exact commit). A branch walk never counts as proven.
19. **Read commit times, not the time of your last look,** before calling a lane silent; the lanes' own clocks drift.
20. **After each plan an independent reviewer checks the facts against the remote and the arithmetic of the finish
    times** before the owner sees it. It found a wave-blocking collision and four wrong rows.

21. **Wind-down mode.** When the number of parallel lanes outgrows what can be tracked, the owner may order: no new
    lanes, no new tasks; each lane finishes what it holds and closes; new findings are recorded as "found, not assigned"
    with their evidence and are not sent to a lane; the board lists every task per lane with its status and is
    republished on each status change; the build lane's replacement is the only successor and takes no new work. Case:
    16 lanes and 113 open tasks.
22. **The coordinator's autonomy boundary: run the work, do not decide for the owner.** Without asking: start, replace
    and close lanes, assign, hold, merge into the build, update the plan, add lessons and checks. Stop for the owner on:
    what the product does, a clash between two of his rules, real orders, merging into the main branch, anything outside
    the repository.
