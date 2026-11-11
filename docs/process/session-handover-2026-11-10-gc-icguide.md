# Session handover 2026-11-10: GC-ICGUIDE (live day moved to Wed 11 Nov)

Contract: `docs/process/goal-contract-GC-ICGUIDE-2026-11-09.md`. Status page rows g01-g38 (kind `icguide`) on the
project status page. Previous handover: `session-handover-2026-11-09-gc-icguide.md`.

## DONE (10 Nov)
- PR #687 merged on main (5a8f5683) before this day; ofo_dev at migration 0050.
- Task 38 part 1: two independent checkers over rows 1-34, no FAIL. Rows 26, 27 and 29 set PARTIAL with named
  remainders (#685 items 8-9); #686 labelled parked; #661 commented (stays parked); row 34 worktree evidence added.
- PATH-63 carries the 25 Jan 2027 chain (commit 58b49b57). On screen (strategy 127, 25 Nov, NIFTY 23,900) the Compare
  now prices the roll into January and refuses it by the playbook's Rs 500 roll limit.
- #689 found and fixed (commit e9137b26 on this branch): the new-adjustment toast was a native `confirm()` that froze
  the whole page; now an in-page toast with Open / Dismiss, plus a source check that no `alert/confirm/prompt` call
  is left in `frontend/src`.

## PENDING
- **Tasks 35-36 (live prices), Wed 11 Nov.** 10 Nov was an NSE holiday (Diwali-Balipratipada); the calendar was not
  checked when the day was planned (my miss). Before the open: confirm 11 Nov is not in
  `backend/ofo/market_calendar.json`; restart the live stack from the main checkout (memory "Live stack start
  commands"); the owner logs in once at `http://127.0.0.1:5173/api/broker/zerodha/login`; then weekly (17 Nov) and
  this-month (23 Nov) paper condors at live prices through the screens, then next month (29 Dec) and two months out
  (25 Jan 2027); watch each and adjust once. Paper only, no Kite order page (ADR-281).
- **Task 37**: intraday live on Tue 17 Nov (expiry day).
- **Task 38 part 2**: check rows 35-37 after they run.
- **Re-screens on test data** (rows 26, 27 and the roll picture of row 29): PATH-60 / PATH-61 warning and 14:30 frames
  after ADR-283, and a wide PATH-63 condor (22000/22200/24200/24400) whose roll is under the limit. Blocked on 10 Nov
  because Chrome stopped drawing any tab (every screenshot timed out, about 3 GB free memory).

## BLOCKED / WAITING ON THE OWNER (none blocks the live day)
- Task 25: read the 23 new texts (`gc-icguide-new-texts-2026-11-09.md`), recommendation accept.
- PR #688 (test databases from a template, 179 s -> 3.2 s per run): owner review before merge.
- OK to drop the 8 old throwaway test databases (`db_run_fresh.py --sweep`).

## PARKED
- Task 22 (#684, real-leg settlement), task 30 (#686, 2027 market calendar).

## NEXT
1. 08:45 11 Nov: calendar check, live stack restart, health and broker status.
2. Owner's Kite login, then task 35, task 36, status rows g35 / g36 stamped from the clock.
3. After the close: the re-screens above, then task 38 part 2 for rows 35-36.

## Notes for the next session
- Moving a scenario frame BACKWARDS answers the new frame number but keeps serving the later prices; restart the
  scenario API and checker to return to frame 0.
- The test-data stack (API 8766, checker, page 5174) and the live stack cannot run together (role `ofo_app` limit 10).
- Worktrees: this branch's (`OptionsForOptions2-path63-jan`), `OptionsForOptions2-toast-689` (its commit is
  cherry-picked here; remove after merge), PR #688's, and two older ones listed in row g34 for the session-end sweep.
