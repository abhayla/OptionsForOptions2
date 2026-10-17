# Builder brief: W-095 round 3 - held position from the net of all plans; finish the core proof (Tier A: order path)

Core: `tests_app/test_execute_route.py::test_core_real_order_entry_then_exit` passes on the real data (strategy id 1;
ENTRY -> BUY 65 NIFTY26O1923650CE LIMIT 3.35 tagged OFS1V1L0; plan 1 closed `filled` {OFS1V1L0: 65}; EXIT -> SELL 65
LIMIT 3.30 tagged OFS1V2L0) and continues: plan 2 closed `exited` {OFS1V2L0: 65}; a THIRD press of EXIT is REFUSED
(net held 0) and nothing is stored.
Proof: that DB test, run once through the main checkout's `db_run.py` with your worktree as cwd, ending with the
shared DB at main's head read from the main checkout.

RCA (Tier A review CRITICAL, round 2): `_held_plan` (execute.py:214-220) took the latest ENTRY plan closed `filled` as
the held legs - written into the brief by the orchestrator - so after a completed exit the same exit is offered again
(SELL 65 on a flat account = a short the user never chose), and after a partly filled entry the exit is refused.
Class: every place the route derives what the strategy holds or may do from ONE plan instead of the net of all its
plans: exit legs, `active_legs` + hash, `version_state`, the reconciliation platform side, the ENTRY-while-held case.
Before: 4 places read one plan / a hard-coded ACTIVE; after: 1 function (net filled units per contract over all plans,
entry/exit signs by side) that all of them call.
Proof: the core test's third-press refusal plus the cases below, each red without its guard (mutation-run).

Tier: A. Model: opus.
Why Opus: a CRITICAL order-safety defect in derived position state across plans; must be fixed at class level.
Budget: 60 min wall-clock, 60 tool calls. HARD limit: at call 56 commit, push, report done / not done / next command.
(Round 2 used 106 of 76: keep this round to the list below; anything else goes in the report as not done.)
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, plus each guard and the
test that went red when you removed it, plus the final `alembic current` line read from the MAIN checkout.
Copy from: none - fixes inside this item's own code.
Findings checked: caller-supplied-verdict-trusted, state-read-after-await, held-without-platform-fill-invisible-to-ledger,
state-with-no-working-exit, repo-wide-scan-outside-targeted-tests, branch-migration-tests-move-shared-db
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

Read first: the Tier A review below, `docs/process/brief-W-095-r2.md` (its Rules still apply), your branch
`build/W-095-execute-route` (head a3155bc), `backend/ofo/execution/safety.py` (`_exit_failure`,
`_exit_product_failure`, `EXIT_NOT_REQUIRED`), `backend/ofo/execution/context.py` (`active_legs_hash`, products).

## Spec basis
- REQ-073 AC-1: "Execute Strategy turns the execution plan (REQ-056) into one Kite basket of LIMIT orders marked read-only, in
    the plan's order; the user cannot change a price, quantity or contract on Kite's page."
- ADR-105 (as corrected in the GC-2c docs batch): held position = the net of Zerodha's filled quantities over ALL the
  strategy's stored plans; an exit closes exactly that net and is refused at zero; a new entry is refused while it is
  not zero (adding to a held position is an adjustment).
- ADR-080: "every exit carries the product of the Zerodha position it reduces (read from Zerodha's position row)"

## Do, in this order
1. `git fetch origin && git checkout -B build/W-095-execute-route origin/build/W-095-execute-route && git merge origin/main`
   (W-094 is on main by now, or `git merge origin/land/W-094` if not; check `git log origin/main --oneline -3`). After
   the merge: `python scripts/ruff_ratchet.py`.
2. ONE function `held_units(plans) -> {contract: signed units}` over every stored plan's orders' `filled_quantity`
   (BUY +, SELL -; None = 0). Use it for: EXIT legs (close exactly the net, opposite side, per contract; refused when
   all zero); ENTRY refused while any net is non-zero; `active_legs` = the net as legs, `active_version_id` =
   `f"plan-{n}"` of the latest plan with any fill, hash via the domain function; `version_state` derived (no fills ever
   = the stored definition is the version executed; a held net = ACTIVE), never hard-coded; the reconciliation
   platform side. Delete `_held_plan`.
3. EXIT products (ADR-080 (1)): `active_products` from Zerodha's positions reply `product` per held contract (already
   read), `exit_products` = the basket orders' product; an unread product blocks (the gate does this when either map
   is missing - fill them).
4. Underlying health: `data_health[UNDERLYING_PRICE]` from the live market context's underlying quote and its age,
   with a test seam; leg-price health from the quote's own time (the depth's frame time), not the read time (review
   MINOR 6).
5. Wrap each synchronous Kite call in the request (orders, positions, funds, basket margin) in
   `await asyncio.to_thread(...)` (review MINOR 4); a contract missing from the catalogue or unresolvable -> the
   catalogue refusal, never a 500 (MINOR 5).
6. Tests (each mutation-run): third EXIT refused at net 0; partial entry {30 of 65} -> EXIT sells 30; ENTRY refused
   while held; open-order refusal at the route (an orders reply with OFS1V1L0 status OPEN, and one with an unknown
   word); `requires_confirmation` refusal; products missing -> refused; the core test with the Pro grant recorded for
   the test user through `entitlement_store.append` (a real grant, not a patched answer).
7. Before push, each as its own command: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py tests/engine/test_pricing_scan.py`,
   `python scripts/ruff_ratchet.py`. Then the ONE DB run (r2's Rules). Commit, push. No PR.

## Tier A review of round 2 (fresh Opus, 2026-10-17 ~07:30 IST): REVISE
1. CRITICAL: after a completed exit a second EXIT builds SELL 65 again (`_held_plan` reads only `filled` plans; exits
   close `exited`; reconciliation skips net-zero contracts; the gate's reduce-only check uses the stale entry legs;
   exits skip the margin check). Related: a second ENTRY after a filled entry is not refused (`version_state=ACTIVE`
   hard-coded, execute.py:443).
2. MAJOR: after a `partial` entry, EXIT is refused with `gate_exit_unverified` while units are held.
3. MINOR: no failing test without: the route's open-order refusal (execute.py:274-275), the `requires_confirmation`
   refusal (322-323), the latest-filled-is-EXIT branch; the interleave test uses one connection (the store's own
   two-connection test proves the lock - keep it that way, and say so).
4. MINOR: synchronous Kite reads block the event loop while the strategy row is locked.
5. MINOR: missing/unresolvable contract -> 500 (KeyError / ValueError) instead of the refusal message.
6. MINOR: leg-quote health stamped with the read time, so it never reads stale; an EXIT needs the feed's last price.
Held by the review: order of operations (no basket without a committed record), margin only from Zerodha, exact tags,
depth-only limits, per-contract reconciliation, the sealed `BasketPost` response.

## Not in this round (report only)
Circuit bands for ENTRY in production (`GET /quote`, a new allow-listed read) - item W-099, next. Until then the route
correctly refuses every ENTRY leg in production as band-unknown; keep the test seam that supplies a band.
