## A5 review (2026-11-24): D-60 strike stepper and leg-edit family, commits ee18a64 and e62bb43

Reviewer: fresh-context helper, read-only, code read; the four named test files 44 of 44. Class: every way a leg is
added or moved in the builder, and every paper entry with a kept duplicate (ADR-319).

Findings:
1. MINOR `StrategyBuilderPage.vue` `askMovedDuplicates` (~740): moved legs are checked against held legs only, not
   against each other; Width or Shift moving two same-action legs onto one contract (Width collapsed to zero) makes a
   silent duplicate row. Class: moved against moved.
2. MAJOR `StrategyBuilderPage.vue` `askDuplicate` / `dupAsk` (~729-736): a newer edit while the question is open
   leaves the old question on screen (or overwrites it); the old promise never settles, so the first `sendEdit` hangs
   and its `finally` (`endMove`, `guard.settle`) never runs; answering the stale dialog is silently dropped
   (`isNewest` false), so Increase does nothing. Fix: settle a pending ask as Cancel when a new edit starts.
3. MINOR same function: moved-leg detection compares `landed[i]` with `baseLegs[i]` by index; a Hedge inserting a leg
   mid-list would raise a false question (not a missed one). Check where Hedge places its leg.
4. MINOR Increase after a move updates `lots` only, not `base_lots`; a later relative control may undo it. Not checked.

Holds: opposite action on one contract asks nothing; Cancel leaves legs, controls and shift total untouched; Increase
uses the picker's lots limit and wording; the page dialog reuses `DUP_QUESTION` and `admitLegs` from `legDoor.js` (only
button labels repeated); Drafts Mode skips zero-lot rows, nets buy and sell pairs by action, sends a same-action
duplicate as separate adds; `_refuse_duplicate_legs` in `paper.py` refuses them with the gate sentence.

Covers the class: mostly yes (gaps: findings 1 and 2).
