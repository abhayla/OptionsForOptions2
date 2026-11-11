# Goal contract GC-IC17NOV: same-day iron condor on live prices (Tue 17 Nov 2026, expiry day)

**Status:** DRAFT for the owner's approval (written 2026-11-11 after GC-ICSAFE).
**Standing direction step:** 1 (the last open live check of the iron condor run; issue #694, GC-ICSAFE row c56,
earlier GC-ICGUIDE row g37). Iron condor depth stays frozen: this run builds nothing new.
**Executor:** `/goal` in a fresh session started before 09:00 IST on Tue 17 Nov 2026, from `main`.

**Core:** a same-day (0 days left) iron condor can be built, watched and adjusted at live prices through the screens.
**Proof:** one strategy on practice money with a value read back at each step.

## Done (results, not steps)

The run is done when all of these are true:

1. One same-day NIFTY iron condor on practice money was built by hand in the builder at live prices, added to paper,
   watched, and adjusted once through the Compare screen; the status page row c56 holds one value per step (index,
   net credit, the adjustment's legs) and a screenshot per step.
2. The 14:30 time-exit rule was seen on that strategy on live prices: absent before 14:30, warning after it.
3. Issue #694 is closed with that evidence, or stays parked with the measured reason it could not be done.
4. Nothing this run started is left running, and the main checkout has no uncommitted file.

If the market is closed that day, or the owner cannot log in to Kite by 10:00, the run stops with a one-line note
on #694 and a new date; that counts as done for this contract.

## Rules

- Paper only (ADR-281 holds; the one real order of ADR-289 belongs to step 4, not to this run). No Kite order page,
  no click inside any Kite order panel.
- Start the live stack from `main` with the recorded start commands; stop only the PIDs this run started.
- Check `backend/ofo/market_calendar.json` for 17 Nov first; check that the PC is unlocked before any screenshot.
- Never write an account figure (margin, funds, P&L of the account) into a file, an issue or the status page.
- Status page rows: update only on a state change, time from the clock.

## Not in this contract

Step 4 (host, sign-in, the real order), the strangle side test, any iron condor change, #692's leftovers.
