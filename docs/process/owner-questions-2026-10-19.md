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

## OQ-GC2h-2: what lifts the block on a contract two strategies share?
- **Case:** strategies 1 and 2 both hold NIFTY 27000 CE; Zerodha's net disagrees with their sum; both are blocked.
  The user closes the position by hand on Kite, so Zerodha now shows 0.
- **Spec basis:** REQ-060 Q224 (owner-confirmed 2026-09-29): on a shared contract "adopt / prepared closing order /
  broker flat -> exited are refused and every holder stays blocked"; "the user resolves by trading in Kite and
  re-running". Q222: "an agreeing reconciliation run does not unblock a strategy by itself". Together: after the user
  trades in Kite and re-runs, nothing can lift the block - the strategies stay blocked for good.
- **Options:** (A) Recommended: when Zerodha shows the shared contract flat, one recorded "Kite flat -> mark exited for
  every holder" action lifts all holders together (no attribution needed: nothing is held); any non-flat state stays
  blocked. (B) An agreeing re-run lifts a shared-contract block (SPEC CHANGE to Q222 for shared contracts). (C) Keep as
  is (blocked until support intervenes).
- **Business call:** it decides when a user's strategies can trade again after a mixed-up shared position.
- Found by the #380-1 fix round (PR #419, 2026-10-19). Needed before GC-3F wires the routes (step 2.2).
