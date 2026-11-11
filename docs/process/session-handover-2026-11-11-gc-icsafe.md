# Session handover 2026-11-11 11:05: GC-ICSAFE, live day done, heading to the one merge request

Read with `session-handover-2026-11-10-gc-icsafe.md` (everything built and reviewed), the contract
`goal-contract-GC-ICSAFE-2026-11-10.md`, the run log `gc-icsafe-run-log.md` and
`owner-questions-2026-11-11.md`. Status page rows c01..c57. Branch `build/gc-icsafe`, work folder
`D:\Abhay\Ventures\OptionsForOptions2-gc-icsafe`.

## In plain words: what today showed

- **The loss alarm really runs with no screen open.** For 30 minutes (09:58 to 10:27) the background watcher checked
  the three practice condors that have the loss alarm switched on 89 times and never once said "margin not known".
  Before this run it said that on every check, all day.
- **Four practice condors were built and adjusted by hand at live prices**, one per expiry kind: this week (128),
  this month (129), next month (130), two months out (131, 25 Jan 2027).
- **The three screen re-checks that a locked PC blocked last night are done** on practice data: the first warning
  and the 14:30 rule on the same-day and weekly condors, the "roll into January" picture, and the new-alert message
  that no longer freezes the page.

## Nothing is running

The live stack was stopped at 10:31 by its 13 PIDs (owner's choice at 10:30: "Stop now", asked because every
remaining step needs it stopped and memory was at 2.3 GB). The practice-data stack and its page server were stopped at
10:57. Ports 6380, 8765, 8766, 5173, 5174 are free. The practice positions 128 to 135 stay stored in the dev database.

## DONE today (evidence in the status rows)

- c07, c08, c09: trading day, login, live prices. c10: weekly and this-month condors. c11: next-month and
  two-months-out condors (131 built 09:52, adjusted 09:54).
- c40: watcher window 09:58 to 10:27, strategies 128 / 129 / 131 = 59 + 15 + 15 checks, 0 "margin missing".
- c17: PATH-60 (strategy 133) and PATH-61 (strategy 134): first warning raised, and at 14:31 the two time rules warn
  (at 14:29 / 14:20 they are absent); never "already true".
- c18: PATH-63 (strategy 135): the roll into January is offered and priced at the entry frame, and refused with its
  reason (over the Rs 500 roll limit) at the 25 Nov frame.
- c19: the in-page "New adjustment opportunity. Open it?" box, page still updating, zero native dialogs.
- c39: the pool-of-one guard file on the final code: 2 passed.
- `origin/main` merged into the branch (two test-tool files of PR #688).
- Leftovers of the live day filed on #692 (items 19 to 25).

## Three things worth knowing (each cost time today)

1. **"0 missing margin" proves nothing for a strategy whose loss alarm is off.** The system default iron condor
   playbook has the "% of margin" stop off by decision (ADR-247). Only strategies on a playbook with it on count
   (today: 128, 129, 131). The watcher log has no per-strategy "T-16 checked" line; a count of margin reads in the
   minute line would make the proof direct (#692 item 20).
2. **After a leg change the loss alarm reads "not checked" for one to two checks** (about 1 minute for a weekly, up
   to about 4 minutes for a monthly, which is checked every 2 minutes). #692 item 19.
3. **Practice-data stack: store frame 0 and restart before building.** The practice checker starts from the frame
   number the previous session stored, and a backwards move is not supported. An alert is raised when a candle
   CLOSES, so on practice data it appears one frame after the frame that made it true. Helper:
   `D:\Abhay\scratch\gc-icsafe\scn.ps1 -PathId PATH-60` (and `-Stop`).

## PENDING, in order

1. c53: `python scripts/orchestrator/prepush.py` under Desktop Commander (about 47 min), marker for HEAD.
2. c54: the ONE merge request (code and docs together), merge on green with `merge.py <pr> --reviewed-sha <sha>`.
3. c55: done-line check by a verifier over the rows that changed behaviour. c44: remove the work folders with
   `wt-rm.ps1` after the merge (count installed packages before and after). c57: final report.
   Before pulling main in the main checkout: its `views/status-page.json` is modified on purpose (identical to the
   branch); restore it first or the pull refuses.

## WAITING ON THE OWNER (none stops the run)

- Q1 approve the demo-ready checklist. Q2 register this app with the shared Notifier (row c25 stays PARTIAL until
  then: the "watcher stopped" alert is built and unit-proven, but cannot reach a phone). Q3 one old work folder.
- Read the new texts listed in the 10 Nov handover. December: load the 2027 holiday list (note N1).

## CLOSED 2026-11-11 16:49 (added after the merge)

- PR #693 merged to main as b8b467de (all 8 checks green on the third run). The run's work folders are removed.
- Contract closed PARTIAL with two rows PARKED: c56 -> issue #694 (expiry day only, Tue 17 Nov), c25 -> issue #695
  (waits for owner answer Q2). Every other row c01..c57 is done.
- Two CI reds before the merge, one class (tests only CI runs pinned behaviour this run changed); the detection step
  is in the run log.

## NOT DONE, by date

- c56: the same-day condor on live prices can only run on Tue 17 Nov (an expiry day). Until then the contract
  closes PARTIAL naming it.

## Rules that bit this run (keep them)

- Finish git writes before dispatching a reviewer: the guard blocks every commit, merge and push while one runs.
- Screenshot timeouts with readable page text = locked PC. A lock-screen process can exist while unlocked: test with
  one real screenshot.
- Stop processes one PID at a time, literal PIDs only; a tree found by parent id can include system processes.
- Never publish `views/status-page.html` over the status page; update rows through the page's database only.
- A background timer of the session can be stopped by the system when memory is short; read the log directly instead.
