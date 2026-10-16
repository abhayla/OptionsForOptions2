# Builder brief: W-085 expiry settlement (Tier A)

Core: a SENSEX calendar holding a leg that expired on 2026-10-15 and a later-expiry leg - after the close the expired leg
is closed at an injected settlement price with a timeline entry, reconciliation against Zerodha positions that no
longer show it reports no mismatch, and the strategy continues with the far leg; a single-expiry strategy whose every
leg expired becomes Exited.
Proof: step 1 is `tests/reconciliation/test_expiry_settlement.py` on real SENSEX contracts of 2026-10-15 from the
recorded catalogue fixtures (grep `tests/fixtures/` for SENSEX rows expiring 2026-10-15 and a later expiry). Write it
FIRST, red.

Tier: A (reconciliation and strategy state). Model: sonnet (builder routing).
Budget: 60 min wall-clock, 64 tool calls. HARD: at call 58 stop, commit, push, report done / not done / next command.
Report: evidence-table, under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no settlement row.

Read first: `docs/process/builder-brief.md`, `work/W-085.md`, `spec/decisions/ADR-083.md`, `spec/requirements/REQ-060.md`,
the reconciliation package `backend/ofo/reconciliation/`
(`compare.py` `MismatchKind`, `triggers.py`), the strategy state machine and timeline (`backend/ofo/strategy/`, REQ-039
transitions, REQ-040 timeline), the risk-message levels in the pre-execution checks (`backend/ofo/execution/safety.py`
flags and `requires_confirmation`), `CLAUDE.md`.

## Spec basis
- ADR-083: "a leg whose contract has expired is closed in the platform at the exchange
  settlement price, with a timeline entry"
- ADR-083: "a strategy with no legs left becomes Exited"
- REQ-060 AC-2: "It detects: missing platform position, unexpected broker position, quantity/strike/side/expiry mismatch"

## What to build
1. Settlement (domain): `settle_expired_legs(strategy, now, settlement_source, clock)` - for each leg whose expiry
   is before `now`'s trading date or whose expiry is today and `now` is after the close (take the close time from an
   existing config/constant if the repo has one; else a named constant with a comment citing F-33's open 15:39 point),
   ask the injected `settlement_source` for the price (Decimal); with a price: close the leg in the platform's books
   through the strategy's proper method, timeline entry naming contract, settlement price, quantity and realized P&L
   (engine formula, ADR-008); without a price: leave the leg open and mark the strategy as awaiting settlement (no
   guessed price). A strategy whose last leg settled transitions to Exited through the recorded transition (REQ-039
   AC-2), never by inference.
2. Reconciliation: an expired-and-settled leg absent from Zerodha's positions is not a missing-position mismatch; an
   expired leg NOT yet settled and absent from Zerodha is reported as awaiting settlement (its own kind, not
   blocking), never silently ignored; an expired leg still PRESENT at Zerodha after the close is shown (Zerodha may
   remove it next morning - ADR-083 unmeasured) without blocking.
## Reviewer checklist (write first; each red when mutated)
- Settled leg absent at Zerodha -> no mismatch; unsettled absent -> awaiting-settlement kind; present after close ->
  shown, not blocking.
- No settlement price -> leg stays open, no default price anywhere.
- Calendar keeps far leg; all legs settled -> Exited via a recorded transition (assert the transition record).
- Realized P&L at settlement from the engine formula (hand-computed expected value).
- Every guard has a killing test; list them.

## Rules
- Targeted tests: tests/reconciliation, tests/strategy, tests/execution, tests/errors separately (conftest collision).
  No database. Then your worktree's own atool `--no-tests`.
- Do not touch backend/ofo/execution/basket.py, backend/ofo/broker/, backend/ofo_app/kite_http.py (W-080), margin code
  (W-081), or the position-grouping files W-083 adds (backend/ofo/reconciliation/ new grouping module). Templates/pins:
  add entries only. No kit/`spec/`/`views/`/findings INDEX; never write `evidence/`.
- Commit, push `build/W-085-expiry-settlement`. No PR.
