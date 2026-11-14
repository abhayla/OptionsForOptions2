Stamp: 2026-11-15 02:47 (from the system clock). DRAFT handover, GC-ICFIX after phase 2 (P1), work branch fix/gc-icfix, head a1b398a5. NOTHING IS PUSHED.
Tracker: https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK (rows u001..u611). Newest older handover: docs/process/session-handover-2026-11-13-gc-icfix-p1.md (its top block covers P0).

## DONE
- Phase 1 (P0): everything buildable is built and checked on the branch; six screen proofs were left (see BLOCKED). Issue 707 (Max profit after the charges really paid) was repaired in a fifth round and merged 887bce70 on 14 Nov, one paisa rounding point for the review and the trade page; issue 707 stays open until the push.
- Phase 2 (P1), 34 of 43 task rows done, all built and merged on the branch:
  - Issue 8 (alerts name trade and rule; bell = Alerts Active): 14acbeff, 56aa9e27.
  - Issue 9 (stop alert on the first check): bcdfe48c. Worst case intraday 75 s -> 15 s, weekly 335 s -> 35 s, monthly 1025 s -> 125 s. Under 30 s holds for intraday only; weekly and monthly intervals unchanged (database load).
  - Issue 10 (exit confirm list warns when cover is lost or max loss more than doubles; says "could not check" when unsure): 6b194cee.
  - Issue 11 (Take profit): works as decided, 9 tests, ae8e4647.
  - Issue 12 (fired rules on the trade page): 01376358.
  - Issue 13 (rules blinking): 6261f779, ADR-309. A fired rule now stays shown until its alert clears.
  - Issue 14 (offer screen shows every applicable approach, "Showing N of M"): 43450f65, ADR-308.
  - Issue 15 (note when a rule set refills the plan box): 33a11250. Target-typing reset not reproducible.
  - Issue 16 (one status function Draft/Running/Completed; closed trades leave Live lists): eb12b45c.
  - Issue 17 (two-expiry estimate curve says it is not a limit): 1811ea80, ADR-307.
  - Issue 18 (re-read up to three times after practice orders, then Retry; Paper tab first): a1b398a5.
  - Issue 19 (open stop kept at the close with its date; reminders read as a sentence; Prepare already blocked on stale prices, so not a fault): fe0a0de1.
  - Item D4 (Adjustment limit reached (2 of 2), closing approaches only): 94f64377.
- New decision rows on the branch: ADR-307, ADR-308, ADR-309.
- Owner answers of 14 Nov: Q4 keep as built (line stays when Profit left is larger than Max profit); Q9 keep as is (closing charges stay assumed in Max profit and Max loss). Run decided by the owner's rule "go with your recommendation": Q7 leave builder folders until the single push, then remove 16, keep -paisa until 707 is done; Q8 leave as built, decide ADR-276 (4) again when real orders return. The Q4/Q7/Q8/Q9 answers still need copying into docs/process/owner-questions-2026-11-13.md on the branch.

## PENDING
- Full local check run 9, started 15 Nov on a1b398a5; result not known when this was written (P1 close rows u331-u335 stay waiting). It replaces the P0 check row u172.
- Nine P1 screen proofs: u205, u214, u224, u243, u262, u284, u292, u303, u323. Each is built and merged; each needs the app copy restarted and a screen pass.
- Restart the live app copy from the branch (API 8765, vite 5173), then do the screens.

## BLOCKED
- u145 (a stop firing on screen), u154 (the 8-order Confirm box) and u214 (stop to pop-up timing) need a market day and the owner's Kite login. Next market day: Monday 16 Nov only if the exchange is open; check the exchange calendar first.
- The live app copy still serves an old head. The session's launch scripts were lost when a helper wiped the session scratch folder on 14 Nov; recreate from the owner's saved note "live stack start commands".

## PARKED
- Issue 10: margin before and after in the exit warning line (ADR-256 asks for it). Reason: not built in two checked rounds.
- Issue 13: "condition met, alert not raised yet" state. Reason: the gate's pending sample lives only in the worker's memory; storing it needs a data change.
- Issue 16: a real trade closed at the broker is not marked closed. Reason: needs a stored field; must be fixed before real orders return.
- Issue 9: weekly and monthly check intervals left as they are. Reason: database load (run decision).
- Issue 15: slow same-day alert speed seen in the test is unexplained (code already defaults to fast). Reason: cannot be reproduced; look on a live day.
- Also open: issue 8 alerts of a closed trade still count in the bell (backend filter, later); D4 a partial reduce is offered at the limit but refused on save; issue 18 why the server read failed in the user test; issue 19 weekday / day-of-month / fixed-date reminders get a generic sentence.

## NOT STARTED
- P2, P3 and the close-out tasks u601-u611.
- The single push happens only on the owner's words "push GC-ICFIX". 26 builder work folders named OptionsForOptions2-gc-icfix-* wait for the push before the removal tool can remove them.

## NEXT
1. Read the run 9 result; if red, repair on the branch and run the check again.
2. Copy the owner answers into the owner-questions file; commit.
3. Restart the live app copy from the branch; do the nine screen proofs.
4. Check the exchange calendar for 16 Nov; if open, with the owner's Kite login do u145, u154, u214.
5. Start P2.

## LESSONS (14-15 Nov)
- Half the P1 items had a different cause than the contract said: prove the fault with a failing test first.
- A review finding is a rule for every later brief (a time without a date was caught twice).
- Run the structure tests on the SUM after merges (five green branches made one red branch, twice).
- A safety warning must fail loud: three states (yes, no, could not check), never two.
- Delete nothing outside your own folder (a helper wiped a shared scratch folder).
