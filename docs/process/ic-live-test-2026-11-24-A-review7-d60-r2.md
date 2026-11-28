## A5 round 2 review (2026-11-24): D-60 commits 27c60cf and 2acaf77

Reviewer: fresh-context helper, read-only; `leg-step-duplicate-d60.test.js` + `leg-duplicate-d60.test.js` 27/27.
Verdict: covers the class: no. D-60 PARKED after two rounds (common rules, section 3 step 8).

Findings:
1. MAJOR `StrategyBuilderPage.vue:~801` with `legDoor.js:25`: after "Increase quantity" the folded leg gets
   `lots = a + b` but `base_lots` is unchanged; `backend/ofo/strategy/leg_edit.py:253` `apply_multiplier` computes
   `lots = base_lots * multiplier`, so a later Lots/Multiplier edit drops the increase (BUY 1 + moved BUY 1, Increase:
   lots 2, base 1; multiplier x1: lots 1). Shift, Width and Hedge pass lots through and are safe. The fold is in the
   shared door, so the picker's Increase has the same gap. Class: a derived field not updated with its source.
2. MAJOR `StrategyBuilderPage.vue:718`: when clicks net to zero (+1 then -1), `moveLeg` calls
   `guard.cancel('leg-edit')` and `endMove` but not `answerDuplicate('cancel')`; the open question stays on screen and
   answers nothing (`isNewest` false). Same class as the round-2 target (one live question per newest move).
3. MINOR: `landed` is computed before the await on the question; after the answer, `legs.value = landed` overwrites any
   change made while the dialog was open (not confirmed that anything can change legs then).

Holds: rapid triple step (the old question is cancelled, the old `finally` runs); step, Cancel, step; Escape and
backdrop map to Cancel; Width collapse checked moved against moved; a numbers reload never touches the question.

Next step for D-60 (parked): (a) in `moveLeg`'s net-zero branch settle the open question as Cancel (one helper shared
with `sendEdit`); (b) in `legDoor.js` Increase, raise `base_lots` with `lots` (test: Increase then multiplier x1 keeps
the total); (c) recheck `landed` against the current legs after the await.
