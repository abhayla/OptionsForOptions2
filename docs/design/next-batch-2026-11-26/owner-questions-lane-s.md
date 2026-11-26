# Owner questions, Lane S (Real P&L on the one Positions list), 26 Nov 2026

Core fact (read from the repo, 26 Nov): Zerodha's positions reply already carries, per contract, `pnl`, `m2m`,
`unrealised`, `realised`, `buy_value`, `sell_value`, `quantity`, `last_price`, `multiplier`, `average_price`
(`backend/ofo_app/kite_reads.py:267` reads them all; `backend/ofo_app/kite_replies.py:273` `positions_from_reply`
keeps only quantity, average price and last price, and `GET /positions` serves units only). Real recorded reply
(owner's live session, 16 Oct 2026 15:10, `tests/fixtures/kite_replies/positions-151006.json`): NIFTY26O1923650CE,
quantity 0, buy 65 at 5.1 (buy_value 331.5), sell 65 at 3.1 (sell_value 201.5), last_price 3.1, `pnl` -130.
-130 = 201.5 - 331.5 + 0 x 3.1 x 1: Zerodha's own formula, `pnl = sell_value - buy_value + quantity x last_price x
multiplier`, reproduces Zerodha's figure exactly from Zerodha's own fields.

## LQS-1 Which figure is "Real P&L"

Spec basis: ADR-330 (10) ("two totals, Real P&L and Paper P&L, never added together"); ADR-008 (one engine produces
every number); ADR-016 / ADR-018 (Zerodha is the authority on actual positions; Zerodha's actual state wins; an
unresolved mismatch blocks). Silent on which figure: none of REQ-044, REQ-109, W-111 or ADR-138 (2) names Zerodha's
`pnl` field or a formula (searched: "real p&l", "m2m", "zerodha p&l", "pnl", "W-111 part 2").

Options:
- (a) **Recommended.** Show Zerodha's own `pnl` per contract, labelled "Zerodha, as at HH:MM:SS". The engine
  re-derives the same figure from Zerodha's own fields (sell_value - buy_value + quantity x last_price x multiplier,
  exact Decimal) and shows it only when the two agree to the paisa; when they differ the row and the total show no
  figure and the reason "Zerodha's P&L for <contract> does not match its own trade values; no figure is shown".
  Serves ADR-008 (the engine's number) and ADR-016/018 (it equals Zerodha's; a mismatch shows nothing). On the real
  case: -130 shown, both agree.
- (b) Engine figure from quantity x (last price - average price). Not chosen: for the real case it gives 0
  (quantity 0) while Zerodha shows -130; after a part close it differs from Zerodha's screen.
- (c) Zerodha's `pnl` shown unchecked. Not chosen: a broken or shaped reply would print a wrong figure with nothing
  to catch it.

Built meanwhile: (a).

## LQS-2 What the "Real P&L" total adds up

Spec basis: ADR-330 (10) ("real contracts are grouped by strategy"); ADR-138 (2) (the list holds only strategy
contracts; outside lots are one count with a Kite link). Silent on whether the total covers contracts closed today or
outside lots.

Options:
- (a) **Recommended.** The total is the sum of the per-row figures the list shows (open contracts of the user's
  strategies), so the user can check it by eye. A line under it says what it leaves out when that applies:
  "Excludes N outside lots and contracts closed today; see Kite for the whole account." Real case: the 16 Oct 15:10
  reply has only a flat (closed today) row: the list has no row and the total reads "Rs 0.00" with that line.
- (b) The whole account's F&O P&L as Zerodha shows it (closed-today rows and outside lots included). Not chosen: the
  total would not equal the rows on screen, and outside lots belong to no strategy.

Built meanwhile: (a).

## LQS-3 A contract shared between strategies, or partly outside

Spec basis: ADR-109 (2) (own lots and outside lots); ADR-018. Silent on splitting one broker figure.

Zerodha reports ONE P&L per contract. When a contract's units belong to two strategies, or part of them are outside
lots (W-111's derived case: 130 held, 65 own, 65 outside), there is no exact split from Zerodha's figure alone.

Options:
- (a) **Recommended.** Fail closed: that row shows no figure with "This contract is shared (with another strategy or
  outside lots); Zerodha reports one P&L for the whole contract, so no split is shown", and the total shows no figure
  with the same reason. Never a guessed split.
- (b) Split pro rata by units. Not chosen: wrong whenever the entry prices differ, which is the normal case.

Built meanwhile: (a).
