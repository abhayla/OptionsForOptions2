# Design #774: a stop must not vanish silently when its leg moves (Change expiry, strike step, Shift, Width)

Spec basis: ADR-330 (42) (Change expiry stages exit-old + add-new), ADR-016..019 (no silent substitution), ADR-330 (6)
and REQ-109 (the per-leg stop is the leg's LTP crossing a set price, ADR-207 (5)), ADR-008 (exact decimal), ADR-317
(a leg stop whose contract is no longer open is cancelled).

Core: after Confirm of a basket that exits contract A and adds A' (same side and lots), an armed leg stop of A is
handled at Confirm, in the same transaction as the orders, and the dialog said so before Confirm.
Proof: one real DB run (tests_app/test_paper_leg_stop_move.py): armed stop on A, basket exit A + add A', read back the
rows of paper_triggers and the dialog lines; today (before) the row stays armed on A until the monitor next tries to
fire it (paper_monitor.py:303), and the dialog says nothing (paper.py:1616 covers index exits only).

## Where stops live
- Table public.paper_triggers (migration 0029): id, strategy_id, kind ('conditional_exit' | 'leg_stop'), direction
  ('above' | 'below'), level (Decimal), contract_id (leg_stop only), underlying (conditional_exit only), fired_at,
  cancelled_at. Store: backend/ofo_app/paper_trigger_store.py (add :118, cancel :125, list_for :130).
- A leg stop is keyed by (strategy_id, contract_id). Its level is a PRICE OF THAT OPTION CONTRACT's premium (the leg's
  LTP crosses above / below it: ofo/checks/leg_price, ofo/tracking/stops.py crossed()). Only one leg-stop kind exists.

## How it is cancelled today on a move
Nothing at Confirm. place_paper_orders (routes/paper.py:1372) stores the orders only. The stop row stays armed on A
(now flat). The monitor cancels it when its level is next crossed / its quote next ticks (paper_monitor.py:303:
"leg_stop and contract not in open_net -> triggers.cancel"), and when the strategy has no open leg (:302). So the stop
disappears silently and A' has none: issue #774.

## Why the stop is not re-pointed (fail-closed)
The level is a premium. A' (other strike or expiry) has another premium: the same number on A' can already be crossed
(it would fire at once and exit the new leg) or sit far from the risk the user meant. No leg-stop kind is
contract-independent (a rupee loss on the leg or a distance would be a new stop kind: a product decision, not built).
So per the fail-closed reading: re-point NOTHING; remove explicitly and say it first.

## Design
1. One function `paper_leg_stops.moved_away(triggers, net_after)` (pure; new file backend/ofo_app/paper_leg_stops.py):
   the armed leg stops whose contract is open now and flat after the orders, when some leg stays open. Used by BOTH:
   - GET .../armed-exits (the dialog preview): one extra line per such stop after the index-exit lines, the server's
     sentence "The stop on <leg> will be removed; set a new one after the move." (catalogue key
     paper_leg_stop_removed_on_move, reviewed: pending owner read). Same reply shape (lines): no openapi change.
   - POST .../orders: after place_checked, in the same transaction before commit, paper_trigger_store.cancel for each
     (one cancel per stop id); a refused / rolled-back set changes no stop.
2. If every leg closes, the existing rule (all triggers cancelled, ADR-317) stands; no line.
3. Dialog: PaperConfirmDialog.vue already renders every armed-exits line; vitest pins a stop line is shown.
4. No migration. No broker call.

## Files / lanes
paper.py (place_paper_orders, armed-exits): shared route file; Lane R's `_hold_until_ready` untouched. No Lane P
(stops rules / PaperStops.vue) file changed; no Lane J plan-watch file; execution_return.py untouched.

## Not built (owner question)
"The stop follows the leg" needs a contract-independent stop kind (rupee loss on the leg, or a premium distance).
Recommendation: owner decides; until then the dialog states the removal.
