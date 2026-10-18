# Owner questions (2026-10-19)

## OQ-GC2h-1: may the app adopt a next-day position as a strategy's own fill?
- **Case:** an ENTRY plan (strategy 1, BUY 65 NIFTY CE) is left open at the end of a trading day; the next morning Kite's
  order and trade lists are empty (they hold today's rows only) and Kite's net shows 65 more units of that contract.
- **Spec basis:** ADR-109 (2): a strategy owns "exactly the fills of orders this app placed"; outside lots are attached
  or detached "by a recorded action, never automatically". ADR-016: Zerodha is the authority. So the 65 cannot be
  told apart from 65 units bought by hand on Kite.
- **Built (GC-2h, spec-conformant):** such a plan closes with a recorded, sticky mismatch; the strategy is blocked until
  a recorded resolution (attach the lots, or reconcile).
- **Question:** keep that (Recommended: no guessed fills; one extra click when it happens), or let the app adopt the net
  automatically (SPEC CHANGE to ADR-109 (2); risk: outside lots silently become the strategy's).
- **Business call:** it decides what a strategy holds and what the user sees as theirs.
- Ask after GC-3L (no real case yet).
