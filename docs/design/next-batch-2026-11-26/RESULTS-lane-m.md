# Lane M results: the leg-stop max-loss line (27 Nov 2026)

Coordinator lines (send_message to "@parent" was refused: `elevated_session_untrusted_device`; written here instead):

- LANE M ALIVE (09:46 IST)
- LANE M RCA (10:00 IST): the "becomes" figure is the engine's true lowest at-expiry P&L of the book left after the
  stop; when the stop leaves a SOLD PUT with no bought put covering it, that lowest point is the index at 0 (strike x
  65 minus the book's cash, about Rs 16.6 lakh for a 25750 PE), and the line printed it as "max loss". The date is the
  ISO record form (`describe_contract`, YYYY-MM-DD) of that uncovered leg in "Sold option with less protection".
  NOT YET EXPLAINED: a stop on the short 25950 CE of a standard 4-leg iron condor cannot leave a put uncovered (same
  engine, B-N1 strikes: Rs 1,712.75 -> Rs 10,487.75), so B-N1's stored book is not the assumed one, or the stop's
  contract is not the short call. The PC SQL below settles it.
- LANE M PUSH 1: see "Push" below (head, gate result, re-test).

Spec basis: ADR-008, ADR-003, ADR-330 (6) (sentence added, PENDING OWNER READ), REQ-151 (contract names as the screens
print them), REQ-100.

## Core proof (failing first, real route, real PostgreSQL)

`tests_app/test_leg_stop_risk.py::test_m1_...` on the app's 25 Nov iron condor (SELL 22800 CE 80, BUY 23000 CE 20,
SELL 22400 PE 130, BUY 22200 PE 34, 65 units): a stop on the LONG put at 5.00. Before the fix the route answered
(read back from the test run):

`If this stop fires, max loss becomes Rs 14,45,535.00 (now Rs 2,860.00). Sold option with less protection: NIFTY 22400 PE 2026-10-13.`

= -22,400 x 65 + 10,465.00: the B-N1 shape exactly (an index-at-0 figure and an ISO date). After the fix:

`If this stop fires, a sold option is left without a bought option of its type covering it, so its loss grows as the index moves past its strike (now Rs 2,860.00). Sold option with less protection: NIFTY 13 Oct 22400 PE.`

The reply's `max_loss_after` still carries the engine figure (`-1445535.00`); only the sentence changes.

## RCA (one sentence)

`routes/paper.py::_stop_line` printed `book_extremes(...).max_loss` of the after-stop book as "max loss becomes Rs X"
even when `exit_risk` had just found a sold option left uncovered, where that figure is the index-at-0 payoff, and the
legs were named with `describe_contract` (the ISO record form) instead of `display_contract` (REQ-151).

Not a cause (checked): lots x lot size (quantities are units end to end), the exit side (`open_legs_to_close`), the
monitor's book (loaded before the exit), the frontend's contract id (`stopLegs` uses the position's own id).

## Class: every place that builds a what-if book for a max-loss or payoff line

| Place | Builds | Uncovered-sold figure printed? | ISO name? | This branch |
|---|---|---|---|---|
| `routes/paper.py::leg_stop_answer` (Stops panel GET leg-stop-risk) | one-leg exit at the level | yes -> fixed | yes -> fixed | fixed |
| `paper_monitor._max_loss_line`, leg stop (fired-stop pop-up and History) | same function, at the fill | yes -> fixed | yes -> fixed | fixed (same code path) |
| `routes/paper.py::index_exit_answer` (index conditional exit, fired) | every leg closed | no (nothing left open) | names via the same reader -> screen form | fixed by the shared reader |
| `routes/paper.py::paper_exit_risk` (exit confirm) | the prepared basket | prints "maximum loss: X before, Y after" | yes (line 1523) | NOT edited: Lane U's file area (exit confirm) |
| plan stop (`adjustment_check.stop_text`) | no what-if book: the record's loss | no | no | none needed |

Size: 3 of 4 what-if sentences fixed (the two leg-stop paths and the index-exit names); 1 left (exit confirm, Lane U).

## Fix (one engine, Decimal only)

- `_stop_line(before, after, uncovered)`: `uncovered` is `bool(risk.exposed)` from the one `exit_risk`; a finite
  after-figure with an uncovered sold option prints the new sentence and no figure. Unlimited (a bare call) keeps the
  existing "no fixed maximum loss". No arithmetic added; no float.
- `names_and_terms`: `display_contract` (the fired-stop body's own form), so every leg-stop and index-exit line names
  legs as the screens do.
- Catalogue: `paper_leg_stop_uncovered`, `paper_leg_stop_uncovered_from_profit` (pins: "pending owner read"); both in
  `STOP_LINE_TEMPLATES` so a stored line reads back.

## Owner question (pending owner read)

Business call: is the new sentence what the Stops panel should say when a stop leaves a sold option uncovered?
Spec basis: ADR-330 (6) "If this stop fires, max loss becomes Rs X (now Rs Y)"; SPEC CHANGE recorded under it.
Recommended: keep it (a number like Rs 16,62,316.50 reads as a forecast; the sentence says what is true and names the
leg). Alternatives: print the engine figure with "(if the index went to 0)"; print both.

## To file as deferred issues

1. B-N1 #194 cause not reproduced: on the PC run and send back:
   `SELECT o.id, o.contract_id, c.name, c.instrument_type, c.strike, c.expiry, o.side, o.quantity, o.price, o.kind, o.placed_at FROM public.paper_orders o JOIN public.catalogue_contracts c ON c.id = o.contract_id WHERE o.strategy_id = 194 ORDER BY o.id;`
   and `SELECT id, kind, contract_id, direction, level, fired_at, cancelled_at FROM public.paper_triggers WHERE strategy_id = 194;`
   If a row's `c.expiry` reads 2028-12-01 the catalogue row is wrong (the screen form "1 Dec" hides the year): a data
   defect, separate from this line.
2. Exit confirm (`paper_exit_risk`, Lane U area): names legs in ISO form and prints an index-at-0 "after" figure for an
   uncovered sold put; same fix as here (`display_contract`, the uncovered sentence).
3. Other `describe_contract` uses that reach a reply's `contract_text` (routes/paper.py lines 604, 637, 878, 1787, 2024):
   check each is reformatted by the screen before it is shown.

## Re-test on the PC (paper only)

1. Pull `hotfix/maxloss-line-1127`, restart the API.
2. Positions > Paper > B-N1 > Stops. Type a stop on the 25950 CE, above 135.00. Expected: if the book is a full iron
   condor, "max loss becomes Rs ..." with a figure of a few thousand rupees; if it reads the new sentence, the stop
   leaves a sold put uncovered: run the SQL in item 1 and send it.
3. Any leg name in the line reads "NIFTY 1 Dec 25750 PE" (no ISO date).

## Push

(filled at push)
