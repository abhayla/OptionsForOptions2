# Owner questions, 2026-10-30

## Q1: should the Positions menu open "Current positions" directly, or keep its section page?

Raised by GC-CLEAN at 01:41 IST while landing PR #604 (owner away; parked here per run-discipline B2, not asked).
Business call: what a user sees when they click a menu item, and which pages the menu reaches, is product scope.
Spec basis: REQ-009 AC-3 "Positions: Current positions, Strategy-linked positions, Adjustment opportunities, P&L/risk."
(the section offers four pages); the GC-TP contract row 4 (owner-approved 2026-10-29) listed a "`/positions`
redirect" (GC-TP step 4b, `frontend/src/router/routes.js`), tied to F-69 (the default Positions tab said the user
held nothing); no decision row changed REQ-009 AC-3.

What happened: the redirect sent the Positions menu straight to Current positions, so the section page with its four
links never showed. Three REQ-009 pages (Strategy-linked positions, Adjustment opportunities, P&L/risk) could no
longer be reached from the menu: CI's navigation check counted 41 menu links, not 45 (PR #604, run on bd543bb7).

Decided for tonight (spec-conformant, technical): the redirect is removed, so REQ-009 AC-3 holds and the screen is
what main already serves. F-69's own fix (the Paper tab as the default when paper positions are open) is unchanged.

Options:
1. **Keep the section page (recommended).** Matches REQ-009 AC-3 and today's main; one extra click to Current
   positions. No spec change.
2. Open Current positions directly AND show the four Positions links on that page (a sub-menu strip), so all four
   stay reachable. SPEC CHANGE to REQ-009's section-page pattern for Positions only; one small build item.
3. Open Current positions directly and drop the section page. SPEC CHANGE: REQ-009 AC-3 loses three menu entries.

Recommendation: 1, because it needs no spec change and loses nothing; choose 2 if the extra click bothers you.
