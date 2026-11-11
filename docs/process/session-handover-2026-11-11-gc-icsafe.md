# Session handover 2026-11-11 09:50: GC-ICSAFE, live day in progress

Read with `session-handover-2026-11-10-gc-icsafe.md` (everything built and reviewed), the contract
`goal-contract-GC-ICSAFE-2026-11-10.md`, the run log `gc-icsafe-run-log.md` and
`owner-questions-2026-11-11.md`. Status page rows c01..c57. Branch `build/gc-icsafe`, work folder
`D:\Abhay\Ventures\OptionsForOptions2-gc-icsafe`. Handed over only because the session's context was full.

## What is RUNNING right now (do not restart; stop only by these PIDs at the end)

Live stack started 08:55 from the RUN'S folder (new code), dev database at migration 0051:
- Redis 5 on 6380: shell PID 6892 (child 22112)
- price feed: shell 10408 (children 11904, 11236)
- API 8765: shell 6572 (children 13396, 12128)
- page server 5173: shell 5304 (child 21796)
- background watcher: shell 18924 (children 22408, 6400); log `%TEMP%\icsafe-live-worker.log` (UTF-16)
- Chrome tab on `http://127.0.0.1:5173/strategy/builder`. The owner logged in to Kite at 09:07; the PC is unlocked.

## DONE today

- c07 trading day confirmed; c08 login confirmed by the app; c09 live prices (NIFTY 25,330.95 at 09:15:55).
- c10 DONE: weekly condor (strategy 128, 17 Nov) and this-month condor (129, 23 Nov) built by hand in the builder
  at live prices, added to paper, each adjusted once through the Compare screen.
- c11 HALF: next-month condor (130, 29 Dec) built and adjusted once. Two-months-out (25 Jan 2027): the four legs
  are picked in the leg picker (buy 25750 CE, sell 25700 CE, sell 25150 PE, buy 25100 PE) but "Done" was not
  pressed; nothing is saved. Start it again from the builder.

## c40 (loss alarm with no screen open): evidence so far, and one trap

- TRAP FOUND: the loss-alarm rule T-16 is OFF in the system default iron condor playbook. "0 missing-margin lines"
  proves nothing unless a watched strategy has T-16 ON. The owner's playbook "My IC copy" (id 13) has it on.
  Strategy 128 was pointed at it at 09:24 (app's own plan PUT); 129 was given it in the plan dialog.
- Watcher log, outcomes per minute (script `D:Abhayscratchgc-icsafet0_log.py <HH:MM>`; it
  joins the wrapped lines and counts `adjust_trigger_missing_margin` per "minute" line):
  09:30 to 09:35: 18 checks, 0 missing margin. 09:37 to 09:47: 35 checks, 3 missing-margin outcomes, each in the
  one minute right after a position change (09:36 after 128's adjustment, 09:43 after 129's, 09:46 strategy 130's
  first check). Steady state is 0. On 2026-11-04 it was 22 per minute.
- Conclusion to record: the watcher reads margin with the day's stored login. Known limit: "not checked" for up
  to about one minute after a strategy's first check or after its legs change (the margin figure is stored per
  set of legs). File this on issue #692.
- Still to do for the row: take one clean window later in the day (say 30 minutes with no adjustments), write the
  counts in the status row, mark c40 done.

## Findings seen on the live screens (file on #692 or as a deferred issue, do not fix in this run)

- After "Add to Paper" an empty dialog box shows for a few seconds before the plan dialog fills in.
- The tracked-legs panel did not refresh prices for about 5 minutes while a dialog was open.
- The Compare screen showed "Margin utilisation 99.4%" for a 1-lot practice condor (looks wrong; not checked).
- Settings-cache warnings in the watcher log: "the poll waited 9.5 s for the database gate (budget 2 s)".
- Never write account figures: the builder shows "Margin available"; keep it out of files, issues and the page.

## NEXT, in order

1. c11: build the 25 Jan 2027 condor on paper through the builder, accept the plan, adjust once via
   `/strategy/builder?adjust=<id>` ("Open in builder and prepare basket" -> "Review and add" -> Confirm). Paper only.
2. c40: the clean window, then mark done. Add the leftovers above to #692.
3. After 15:30: stop the live stack by the PIDs above. Then c17, c18, c19 on test data (scenario stack: API 8766
   with `APP_ENV=development`, `OFO_SCENARIO=ADJ-60` / `ADJ-61` / `ADJ-63`, checker, page 5174; never beside the
   live stack). PC must be unlocked: check `Get-Process -Name LogonUI` first.
4. Refresh the handover, merge `origin/main` into the branch (main has PR #688 since last night), run
   `python scripts/orchestrator/prepush.py` under Desktop Commander (about 47 min; passed last night on 64576e81),
   then c54: ONE merge request (`land.py` or push + `merge.py <pr> --reviewed-sha`), merge on green.
5. c55 done-line check by a verifier, c44 remove the work folders (`wt-rm.ps1`; after the merge), c57 final report.
   Before pulling main in the main checkout: its `views/status-page.json` is modified on purpose (identical to the
   branch); restore it first or the pull refuses.
6. c56 is Tue 17 Nov only. c25 waits for owner answer Q2. Q1 and Q3 are also open.

## Rules that bit this run (keep them)

- Finish git writes before dispatching a reviewer: the guard blocks every commit, merge and push while one runs.
- Screenshot timeouts with readable page text = locked PC.
- Stop processes one PID at a time; a tree found by parent id can include system processes.
- Never publish `views/status-page.html` over the status page; update rows through the page's database only.
