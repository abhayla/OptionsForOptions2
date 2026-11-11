# Session handover 2026-11-10 (night): GC-ICSAFE

Contract: `docs/process/goal-contract-GC-ICSAFE-2026-11-10.md` (standing direction steps 1 to 3). Status page rows
c01..c57 on the project status page. Run log with the reuse map, deviations and the old-branch table:
`docs/process/gc-icsafe-run-log.md`. Owner questions: `docs/process/owner-questions-2026-11-11.md`.
Everything below is on branch `build/gc-icsafe` in the work folder `D:\Abhay\Ventures\OptionsForOptions2-gc-icsafe`.
Nothing of this run is on main yet except PR #690 (the standing direction file).

## In plain words: what a user gets from this run

- **The loss alarm now runs with no screen open.** The background watcher uses the day's broker login to read margin.
  Before, it said "not checked" on every strategy, all day.
- **You are told when the watcher stops** (built and tested; the message cannot reach your phone until the app is
  registered with the Notifier, question Q2).
- **The calendar no longer fails silently on 1 Jan.** From 1 Dec a banner and a daily alert say the list ends; a date
  without a list says so instead of "market closed".
- **The daily contract list loads without a hand-push** when Zerodha only changes the strike range.
- **Two screens no longer hang** when database connections are short, and the practice-order limit check was kept
  correct while fixing that (a review caught that the first fix had broken it).
- **Iron condor loose ends closed:** alerts raised for a position you already changed now lapse (also after a
  restart); the alert shows the same limit as the panel; four labels say what the rule really does.

## DONE (each with its evidence on the status page)

- Set-up c01..c06; core proof c12 (a process with no screen read the stored login and made one margin read).
- Finish line c20, c21: `demo-ready-checklist.md` drafted, approval question Q1 filed.
- Iron condor faults c13..c16; first-user fixes c22..c24, c26..c33, c35..c39; own read c45; reviews c46..c49 (five
  reviews: 2 passed, 3 found 6 real problems); fix rounds c50, c51; second strict check of the six: passed.
- Clean-up c41 (PR #688 reviewed twice, real-server proof, pushed), c43 (old branches table).
- Decisions written: ADR-284 (contract-list guard), ADR-285 (calendar end), ADR-286 (Notifier address allowed;
  heartbeat at 2 minutes; one alert per change of state).
- Deferred issues filed: #691 (test-database tool leftovers), #692 (14 small leftovers of this run).

## PENDING

- **Live day, Wed 11 Nov (rows c07..c11, c40).** Needs the owner's Kite login from 09:00. Steps: confirm the date in
  `backend/ofo/market_calendar.json`; bring the dev database to migration 0051 (owner role, as done for 0050);
  start the live stack FROM THE RUN'S WORK FOLDER (not the main checkout), so the new watcher code runs; then the
  weekly and this-month condors (c10), next-month and two-months-out (c11), and for c40 read the worker log between
  two named times: count of checked T-16 lines above 0 and count of `adjust_trigger_missing_margin` equal to 0.
- **Screen re-checks on test data (c17, c18, c19)**: PATH-60 / PATH-61 warning frames, the PATH-63 roll picture,
  and the in-page toast.
- **c34**: the day's contract-list refresh with no force on the dev database (log line with `grid_change_left`).
- **c42**: PR #688 merges when its long database check is green (`merge.py 688 --reviewed-sha 8c43ba77...`).
- **c52..c55, c57**: this note kept current, the full pre-push check, the ONE merge request, the done-line check,
  final report. The contract puts the merge request after the live proof (c40).
- **c56**: same-day condor on Tue 17 Nov only.

## BLOCKED / WAITING ON THE OWNER (none stops the run)

- Q1 approve the demo-ready checklist. Q2 register this app with the shared Notifier (needed for any phone alert;
  row c25 stays PARTIAL until then). Q3 delete one old work folder whose unsaved notes are already saved elsewhere.
- From the earlier run: read the new texts (now also: "The position changed", the no-calendar reason, the two
  banner texts, four trigger labels, "Max profit (if the index falls to 0)", five alert texts).
- December: load the 2027 holiday list (note N1).

## PARKED

- Nothing parked by this run. Two fix rounds were needed on #682, #685 item 3 and the warnings; all closed in
  round 2.

## NEXT

1. 08:45 on 11 Nov: calendar check, dev database to 0051, live stack from the run's folder, health check.
2. Owner's Kite login, then c08, c09, c10, c11, c40, c34.
3. Screen re-checks c17..c19 (any time; test data).
4. Pre-push check, the one merge request, merge on green, done-line check, final report, remove the work folders.
5. After this contract: standing direction step 4 (host, a second login, a real order at 1 lot) and the short
   strangle side test, each under its own contract.

## Notes for the next session

- The project guard refuses every git write while an independent reviewer runs. Finish merges and pushes BEFORE
  dispatching reviewers; builders told to commit will wait.
- Builder work folders `OptionsForOptions2-icsafe-*` (680, 682, 685a, 685b, 686, 627, hb, fe) are merged into the
  run's branch; remove them with `wt-rm.ps1` when the merge request has landed. Never link `node_modules` from the
  main checkout (a guard blocks it): run `npm ci` in the folder.
- Database test files over the tunnel are slow (one 22-test file took 23 minutes). Run the two or three nearest the
  change with the fast tool from PR #688; the full database suite is the merge request's automatic check.
- A process tree found by parent id can contain unrelated system processes (reused process numbers): stop only
  the PIDs you started, one by one.
- Log files written by PowerShell `*>` are UTF-16: read them with that encoding, or a search finds nothing.
