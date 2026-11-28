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
11. **CI runs only on pull requests and the main branch,** so lane branches cost no CI. Count the merge into main in the
    plan from the start. A main that is 11 days and about 1,700 commits behind made every check judge hundreds of files:
    about 15 minutes of waste per push (E).
12. **One line per new lane to the owner:** what it finishes that a running lane cannot.
