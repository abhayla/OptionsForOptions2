# RESULTS, Lane B (Phase 5: one leg door, ADR-328 (1)/(2), ADR-329)

Branch `refactor/leg-door` cut from `a99730b8`. State: every Phase 5 commit EXCEPT the one that edits
`frontend/src/pages/StrategyBuilderPage.vue` (5.5.4), which is Lane A's file until the hand-over (PLAN 3.2). Paper only; no
order endpoint touched; no spec file edited (so 5.5.0, the ADR-007 Q34 / ADR-319 (1) sentences, is NOT done: it needs the
coordinator's wording and Lane A's spec rows). New decision numbers used: none (ADR-331 not needed).

## Done (commits, in order)

- tests first (red): `leg-door-phase5.test.js`, `builder-draft-replace.test.js`, `builder-hold-adr329.test.js`,
  `leave-builder-adr329.test.js`, `chain-trip-adr329.test.js`, `helpers/phase5Wired.js`; new `it`s in `leg-duplicate-d60.test.js`;
  two existing `it`s changed with their reason (see Tests)
- 5.5.1 `lib/legDoor.js`: `oppositeContract`, `opposite: 'allow' | 'ask'` on `admitLegs`, `OPPOSITE_QUESTION`, `OPPOSITE_NOTE`, `sameLegs`
- 5.5.2 `composables/useLegDoor.js` (one pending slot; `ask`, `answer`, idempotent `cancel`, `admit`, `admitMoved`) and
  `components/strategy/DuplicateLegDialog.vue` (same test ids; opposite kind shows Keep both / Cancel only)
- 5.5.3 `LegPicker.vue`: `inject('legDoor', null) ?? useLegDoor(...)`; renders its own dialog only when it made its own door;
  stale-legs guard (content compare `sameLegs`: a replaced list = Cancel, an equal-content refresh keeps the answer)
- 5.5.2a `stores/builderHold.js`, `composables/useLeaveBuilder.js` (router-leave guard, `unsavedCount`, `leaveQuestion`),
  `components/strategy/LeaveBuilderDialog.vue`
- 5.5.3a `OptionChainPage.vue`: the leave guard only (`openBuilder` / `addSelected` untouched)

## Tests (names, red to green)

Red run (evidence `evidence/lane-b-red.txt`, `LANE_B_FORCE=1`, 8 files, source modules absent): 8 files failed, 7 tests failed, 59 passed, 2 skipped
(four new files failed to import their modules). Green with the code (no force): 8 files passed, 99 passed, 32 skipped.
Full vitest (all 228 files): 228 passed, 2665 passed, 32 skipped.

Page-dependent tests are gated by `tests/helpers/phase5Wired.js`: they run when `StrategyBuilderPage.vue` contains `useLegDoor`
(door rows), `draft-replace-dialog`, `useBuilderHold`, `useLeaveBuilder`; `LANE_B_FORCE=1` runs them now. Forced today: 25
fail (expected, all need the page), 104 pass. They are THE PAGE COMMIT'S TESTS and were never run green against a wiring (the page
was not editable), so expect small adjustments:
- `leg-door-phase5.test.js`: rows 1, 2, 3, 4, 10, Drafts Mode row 2/3, 12 (page half), 7 (page half)
- `builder-draft-replace.test.js`: the five "asks" tests (the three "asks nothing" tests and the refusal pin pass today)
- `leave-builder-adr329.test.js`: real-page rows L1-L7 (harness rows, chain-page rows L11, L10 scan pass today)
- `chain-trip-adr329.test.js`: C1-C6, C8-C12 (C7 passes today)
- `leg-step-duplicate-d60.test.js` (opposite step asks) and `draft-link.test.js` ("Replace the N legs" then Yes)

Green now: door unit rows 5, 6, 7, 8, 9 (door level), 11, 12 (picker half), 13, the picker stale guard, `builder-hold-adr329.test.js` H1-H4
(14 tests), the leave guard on a harness (L1, L3-L5, L7, L11), L11 on the real Option Chain page, L10 (no `beforeunload` in `src`).

Changed existing tests (reason in the tests commit): `leg-step-duplicate-d60.test.js` "other action does not ask" now `skipIf(door wired)`, with the
ADR-328 (1) test beside it; `draft-link.test.js:265` same pattern for ADR-328 (2). The page commit deletes the two `skipIf` stand-ins.
Row 5 of the plan (picker add of the opposite side silent) is covered at the door level here and by the unchanged
`leg-duplicate-d60.test.js:161`; rows "ready-made" and "Compare" of row 11 are not re-tested (existing `ready-made.test.js` unchanged and green).

## Gates

- `tools/ci_local.py`: see the last line in the report (shallow clone made `git merge-base origin/main` fail; fixed with `git fetch --unshallow`).
- `select_app_tests.py` on this lane's diff (backend/ is untouched): selects nothing, so no `tests_app` DB run. The CLI's default
  diff (`origin/main...HEAD`) lists 269 files because it includes Lane A's Step 0 backend work; none is from this lane.

## Parked

- Drafts Mode restore on the return from the chain (PLAN 5.5 may park it): part of the page commit; test C11 is written. Not attempted (page not editable).
- Step 5.5.0 spec sentences (ADR-007 Q34, ADR-319 (1)): not done, Lane B may not edit `spec/`.

## What the page commit still needs

See `lane-b-page-commit-draft.md` (eight numbered steps, unvalidated draft code).

## Screen checks (owner, click by click; placeholders)

Wait on the page commit: all rows below except the first.
1. Same-side step (a step onto a contract held with the same action): Increase quantity / Keep separate / Cancel. Works today and through the new dialog (picker alone): [ ] seen.
2. Opposite-side step (SELL stepped onto a held BUY): "NIFTY ... is already in this strategy as a Buy." / "A Buy and a Sell of one contract cancel each other out." / "Keep both" / "Cancel". [ ] wait on page commit.
3. Chain trip keeping legs: 3 unsaved legs, Market > Option Chain, tick 2, Add Selected: 5 legs, no question. [ ] wait on page commit.
4. Chain trip adding legs with a clash (same action): the usual three-button question; Cancel adds nothing. [ ] wait on page commit.
5. Leave question: "Leave the builder? The N unsaved legs will be lost." Stay / Leave, from the builder and from the chain with a hold. [ ] chain page half can be checked now (hold needs the builder half); builder half waits on page commit.
6. Replace question on a draft link: "Replace the N legs in the builder?" [ ] wait on page commit.
New wording to read: the opposite note, the singular "The 1 unsaved leg will be lost.", the Drafts Mode changed-book sentence (not yet in code).
