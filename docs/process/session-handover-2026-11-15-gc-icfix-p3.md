2026-11-15 11:55 IST. GC-ICFIX handover after the third (P2) and fourth (P3) priority groups. Branch fix/gc-icfix, nothing pushed.

## Status of the check (read first)
- The full local check passed on head b3b2911a (run 13): `TOTAL PASS 2138.6s`, log `D:\Abhay\scratch\gc-icfix-backup\prepush-run13.log`.
- This records commit came AFTER it, so the pass marker is for b3b2911a. A new full check is needed before the push.
- Backup of that head: `D:\Abhay\scratch\gc-icfix-backup\gc-icfix-p3-b3b2911a.bundle`.
- The single push happens only on the owner's words "push GC-ICFIX".

## DONE (merged on the branch)
Third group:
- Issue 20: a strategy with only practice orders can be deleted and undone; a broker basket, a saved version or a position held at the broker refuses (ADR-312; 81ae3388).
- Issue 21: a completed trade shows its adjustment history; a refused Compare links to it (b5ddeab5).
- Issue 22: the clock rule alerts on expiry day only, named "Time exit (on expiry day)" (ADR-310; 6813acb3).
- Issue 23: a rule true at entry works as decided: six pins, one finding (024db44a).
- Issue 24: with a leg without a price the totals stay paused, the leg is named, priced legs keep their figures, Booked after charges always shows (ADR-311; 68395242).
- Guided builder: a condor-family strategy whose sold strikes sit above the entry guide's ceiling 0.20 shows the server's line (a6205525).
Fourth group:
- u502/u505/u513: Save is on only when the legs differ from what the server holds, on when unsure; a dialog's preview is not counted as pending; the captured line keeps its space (b84b1599).
- u504/u506/u511: menus list only built pages, "/" opens My Strategies (ADR-313); pop-ups bottom right below dialogs; opportunities list in pages of 25 (4af67664).
- u507: Greeks at target carry their basis and server-rounded figures (74fb4b2b).
- u509: approach names say only what the code always does (f65158b9).
- u510: one helper for every expiry text; the year shows unless the expiry is in the shown date's year, and always when no date is known (2b1e37d7).
- Repairs: seven structure tests (two real duplicated constants; one apostrophe in a comment broke a scan and failed three tests); a performance regression (the entry-guide line computed deltas a second time, now read from the shared computation; 0ebcdaea); one stale description file.
- Decision rows written under the owner's rule of 14 Nov: ADR-307 to ADR-313.
- Checked, NOT faults: u503 (name is plain text; rename exists); u512 (default charge rates match the broker's public page; the Rs 25 per order in the user test is unexplained, live setting row unread); u510 "Monthly on a Monday" (23 Nov 2026 is the real monthly expiry, 24 Nov is a holiday in `backend/ofo/market_calendar.json`); u501 title dashes (one live style; mixed dashes were old stored alerts).

## PENDING (needs the app running)
- Issue 25 (status words on every list: a screen check), issue 26 (app slow under load: measure first), u404 (clear about 70 old practice trades on screen).
- No on-screen proof exists for the second, third or fourth group.
- Close-out tasks u601-u611 not started.

## BLOCKED
- The two P0 live screen checks (u145, u154) and u214: need a market day and the owner's Kite login.
- The live app copy serves an old head and its launch scripts were lost; recreate from the owner's saved note "live stack start commands".
- About 40 builder work folders named `OptionsForOptions2-gc-icfix-*` wait for the push before the removal tool can remove them.

## PARKED (issue 709; each needs a stored-data change)
(a) which approach an adjustment used is never stored; (b) the "about" price confirmed at is not stored (u508; quoted 51.00, filled 51.40); (c) a real trade closed at the broker is not marked closed (fix before real orders return); (d) "condition met, alert not raised yet" state; (e) naming the day in reminders; (f) margin before and after in the exit warning (ADR-256).

## DEFERRED (found outside the done list)
1. Roll logic, three findings: issue 708 (`backend/ofo/adjustment/approaches.py`).
2. Money in two digit groupings: Indian in the engine formatter and `frontend/src/lib/displayFormat.js:189,198`; western at `backend/ofo/gate_slots.py:152,189`; "Rs " 6 times in `backend/ofo/errors/explanations.py`.
3. Percent sign spacing: about 35 texts "1%", about 16 "1 %"; a change needs former-text entries for stored alerts.
4. Dates in three shapes on about 5 screens.
5. "Monthly" decided by two rules (`frontend/src/lib/guided.js:43-56`, `expiry_kind_of` in `backend/ofo_app/adjustment_readers.py:686`).
6. Server-built contract names not checked for the year rule.
7. `frontend/tests/option-chain.test.js` failed twice in whole-suite runs beside a database job, passed alone six times.
8. The structure scan for index tables gives up on a file when a comment holds an apostrophe.
9. At the adjustment limit a partial reduce is offered but refused on save.
10. Alerts of a closed trade still count in the bell (filter is `deleted_at IS NULL` only).
11. Decay vs Theta help text implies they differ only by days; bases differ (Decay holds spot fixed, Theta is on the forward).
12. Trade 142's stored starting value for its delta rule was never read.
13. Why the server read failed after placing orders in the user test is unexplained (page now retries).
14. Three browser-level test files edited or added, not run: `frontend/e2e/navigation.spec.ts`, `responsive.spec.ts`, `toast-clear.spec.ts`.
15. Live brokerage setting row unread (Rs 25 vs default Rs 20).

## Lessons
- The full check failed twice on the sum of branches that each passed alone: run its first gate after every merge batch, not a hand-picked list.
- A reviewer's "cost unchanged" is answered by the test that counts the work.
- A pop-up was moved three times and ended where it started: nobody located the thing it must not cover.
- A repair "in general" must be checked in every state the old code handled (Booked figure; Save button's lost-work path).
- Time and step limits written in a brief stopped no reviewer or builder.

## NEXT
1. Owner: a market day plus Kite login for u145, u154, u214; start the app per the saved note.
2. Run the screen checks (issue 25, 26, u404) and the missing screen proofs.
3. Run the full local check again on the final head, then wait for "push GC-ICFIX".
4. After the push, remove the builder work folders with the removal tool; start u601-u611.
