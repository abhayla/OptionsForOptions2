# Session handover: GC-ADJ1 (adjustments core), 2026-10-30 / 31

Branch: everything is on `build/gcadj1` (run tree `OptionsForOptions2-gcadj1-run`); the merge into `feature/adjustments` is NOT done yet (see BLOCKED). Nothing was pushed, no PR was opened,
main was not touched (owner rule 2026-10-30, written into the contract's Owner decisions as the run's first commit).
Contract: `docs/process/goal-contract-GC-ADJ1-2026-10-30.md` (progress log section 0.3, "Found during the run" rows
1-22 hold every decision taken in the run).

## DONE

- Step 0: overlap check (no approach code existed).
- Step 1 (REQ-155, W-196): `POST /api/strategies/{id}/adjustment-approaches` builds the 7 iron condor approaches
  (A-36, A-01, A-05, A-29, A-28, A-11, A-31) and prices the whole-trade After (booked P&L once; this-adjustment, paid,
  open-exit charges as separate lines), POP under the held switch, Zerodha margin with its state, spot feed -> REST ->
  last close. Fixed F-74, F-75 (POP class now guarded), F-76. Dev-server proof: ADJ-02 / ADJ-13 approach figures equal
  the scenario generator's engine-free values to the paisa; engine 0.009-0.023 s for 7 approaches.
- Step 1b: scenario mode (`OFO_SCENARIO=ADJ-xx`, development/test only, refused at start-up elsewhere, every order
  route refused, banner on every screen), seed script `scripts/seed_scenario.py` (strategies 72 = ADJ-02, 73 = ADJ-13,
  74 = ADJ-01 on ofo_dev).
- Step 2 (REQ-156 W-197, REQ-157 W-198): compare in Strategy Builder adjust mode (`/strategy/builder?adjust=<id>`),
  five criterion groups with leaders, "Leads on N of M", filters from the current approaches.
- Step 3 (REQ-046 W-199): "Review adjustment" on the strategy's tracking panel -> drawer (layers 1-3, no numbers
  before a pick) -> Compare with the picks -> "Open in builder and prepare basket" (legs only; no order).
- Checks: Tier A Opus on every money / broker / start-up piece, Tier B on the approach builder; walked in the owner's
  Chrome in scenario mode (ADJ-02, ADJ-13, ADJ-01).

## PENDING (deferred MINOR findings, shipped listed)

1. `_closed_booked` (booked P&L of legs an approach closes) still computes in `backend/ofo_app/routes/adjustment.py`
   instead of the engine (ADR-008); values verified equal to the hand values. A builder reported it moved; it was not.
2. An empty Zerodha basket-margin reply is worded "could not be read just now" (never 0, REQ-155 AC-6 holds). A fix
   that split "empty" from "unreadable" regressed the outcome page for ambiguous replies and was backed out.
3. Compare display: the POP filter range shows raw decimals (0 - 0.744067755) and the debit/charges ranges show no
   rupee sign; "Margin needed" in the current state is unformatted; the leader label "Smallest margin change" goes to
   the approach that frees the most margin (wording).
4. Phone width (390 px) not verified in Chrome (the window would not resize); only a component test covers it.
5. Frontend fixtures `adjust-*-adj13.json` were captured before the scenario funds fix (margin "unreadable"); recapture.
6. Scenario stand-in margin is a test formula (SELL strike x qty x 0.12 minus BUY premium), far above real SPAN
   (e.g. 715,552.50 for a 2-lot NIFTY condor); test data only, never reachable outside scenario mode.
7. "Adjustments used" shows "-" everywhere: the paper book does not record adjustments yet (comes with GC-ADJ2 history).
8. 115 new user-facing texts are pinned "pending owner read" (counted with `git diff 7fdcd8dc..HEAD -- tests/errors/template_pins.json | grep -c "pending owner read"`) in `tests/errors/template_pins.json` (approach names,
   explanations, refusals, leader labels, spot reasons).
9. Live check owed: a real Kite read of `NSE:NIFTY%2050` through `fetch_index_quote` (optional in this contract).

## BLOCKED / owner

- Step 4 not closed: `python scripts/orchestrator/prepush.py --repo D:/Abhay/Ventures/OptionsForOptions2-gcadj1-run --full` was started at about 23:37 and stopped by Claude Code because the machine ran critically low on memory (not a test failure; no result was produced). The contract requires it to PASS before `build/gcadj1` merges `--no-ff` into `feature/adjustments`, so that merge has not happened. Next, once memory allows (close other apps and Claude sessions first): (1) re-run that prepush command; (2) only if it PASSes, in the run tree: `git checkout feature/adjustments && git merge --no-ff build/gcadj1 && git checkout build/gcadj1` (local only; nothing to main, no push).

- Q2 in `docs/process/owner-questions-2026-10-30.md`: should "Exit whole strategy" lead the Greeks rows only because
  nothing stays open (Exit leads 5 of 18 on ADJ-02, 6 of 18 on ADJ-13)? Recommendation: show "No position left after
  exit" and exclude Exit from leading those rows (SPEC CHANGE to REQ-156 AC-3).
- Worktrees cannot be removed: `wt-rm.ps1` needs the branch on origin/main, and the owner rule keeps this work off
  main (contract row 11). Kept, all merged into feature/adjustments, no node_modules except the run tree's own copy:
  `OptionsForOptions2-gcadj1-run`, `-gcadj1-pop`, `-gcadj1-spot`, `-gcadj1-appr`, `-gcadj1-scen`, plus agent
  worktrees under `.claude/worktrees/agent-*` from this run.
- Stray file `D:\tmp_a.log` (345 bytes, a builder's test log): deletion was blocked by the safety check; please delete.

## PARKED

None.

## NEXT

1. Owner: answer Q2; read the pinned texts (PENDING 8); approve the iron condor playbook numbers before GC-ADJ2.
2. GC-ADJ2 (playbooks, plan sheet, inbox, history; REQ-158..163), outline at the end of the GC-ADJ1 contract.
3. GC-ADJ3+ (owner 2026-10-30: outline for approval) - catalogue features in no contract yet:

| Contract | Features (catalogue ids) | Depends on |
|---|---|---|
| GC-ADJ3 Cost and honesty | F-04 full cost line incl. cost as % of premium left (T-19), F-12 liquidity guard on strike pickers, P-02 fresh-trade view polish, PENDING 1-5 above | GC-ADJ1 |
| GC-ADJ4 More strategy types | approaches for short strangle / straddle, iron fly, credit and debit spreads, long options, calendars, ratios, butterflies (scenarios ADJ-30..41 exist), remaining A-ids (about 28 of 35) | GC-ADJ1, GC-ADJ2 playbooks |
| GC-ADJ5 Triggers | T-03, T-05, T-06, T-07, T-09, T-10 clock, T-18, T-19 on top of T-01/T-02 | GC-ADJ2 |
| GC-ADJ6 What-if and paper adjust | F-05 spot/IV/date sliders on the After, F-19 paper-adjust a real position | GC-ADJ1 |
| GC-ADJ7 Time-of-day help | F-14 morning summary, F-15 15:00 carry check, F-16 expiry-day mode, F-09 event calendar (admin list - owner decision 9b-3) | GC-ADJ5 |
| GC-ADJ8 Deeper analysis | F-10 delta-neutral helper, F-13 P&L attribution, F-18 adjustment effectiveness, F-20 explainers per action | GC-ADJ2 history |
| Later | F-22 backtest (needs a data licence), automatic features F-A1..A8 (SPEC CHANGE, legal Q211) | owner |

4. When GC-ADJ2 is done: one PR takes the whole feature to main, only with the owner's explicit approval.
