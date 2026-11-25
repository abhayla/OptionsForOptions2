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

## Phase 5 page commit (5.5.4) and merge: DONE (25 Nov 2026, overnight)

- Merge of Lane A Phase 4 (`87a446bf`): `0b5aff70`, no conflicts. Lane A's `exitOrigin` / `exitBlocked` gate in `reviewPending` /
  `confirmPending` and the `pendingOrders` watch (ADR-328 (4)) are on the page and untouched. Digest, spec index, build order and
  coverage checks current. Removed-vs-called grep (symbols either side removed, both directions): nothing dangling.
- Page commit `463c9ad1`: one door (`useLegDoor`, `provide('legDoor')`, one `DuplicateLegDialog`); `door.admitMoved` in `sendEdit`;
  old `dupAsk` / `askDuplicate` / `answerDuplicate` / `askMovedDuplicates` and the second "Already in this strategy" Modal removed;
  ADR-328 (2) replace question (`draft-replace-dialog` / `-yes` / `-cancel`; a second link settles the first as Cancel; an open leg-door
  question closes when the replace question opens); `useBuilderHold` `take()` before `legs`, `?strategy=` / `?adjust=` clears it;
  Add Selected through `door.admit(..., { opposite: 'allow' })` as `chain-<n>` legs; `useLeaveBuilder` + `LeaveBuilderDialog`;
  Drafts Mode restore with the `netKey` check (test C11 green in round 1, not parked).
- Tests red to green: the 25 page-dependent tests (and the 7 skipped rows of the gated files) now run WITHOUT `LANE_B_FORCE` and pass.
  Full vitest: 230 files, 2728 passed, 0 skipped (before the page commit: 2698 passed, 32 skipped). The two `skipIf` stand-ins are deleted.
  Test-side fixes to never-run tests (all harness mistakes, none weakened an assertion): `editLeg` not awaited while its question is open;
  reply legs carry `contract_id` / `lot_size`; a fresh chain selection per trip (C2); C4 starts the held leg at the served maximum
  (10000) instead of editing the leg after the question opened; C12 allows the chain page's own `GET /market/chain`; the d60 round-4
  "new ?draft=" test now answers the replace question with Yes (item 8; no other mounting test pushed a second `?draft=`).
- Spec notes: ADR-007 Q34 and ADR-319 (1) dated notes landed (`5124d06f`); digest regenerated, unchanged.
- Gates: `ci_local` 16 passed, 0 failed, 5 skipped. `select_app_tests` on this lane's own commits (merge to HEAD): 0 backend files, 0 files.
  Against `75f7ae65..HEAD` it selects 160 `tests_app` files, all from Lane A's merged backend work (9 backend files), not from this lane;
  they were not re-run here (Lane A's own Phase 4 gate covers them).

## Parked

- Nothing parked: the Drafts Mode restore (C11) is built and green.
- Step 5.5.0 spec sentences: done (see above).

## Screen checks (owner, click by click)

Paper only. Open the Strategy Builder (Strategies > Strategy Builder).
1. Same-side step. Add SELL NIFTY 22800 CE and SELL 22700 CE (two legs). On the 22700 leg click the strike "+" until it would land on
   22800. Expect "NIFTY ... 22800 CE is already in this strategy." with Increase quantity / Keep separate / Cancel. Cancel: legs unchanged. [ ]
2. Opposite-side step. Add BUY 22800 CE and SELL 22700 CE. Step the SELL leg onto 22800. Expect "NIFTY ... 22800 CE is already in this
   strategy as a Buy." and "A Buy and a Sell of one contract cancel each other out.", buttons Keep both / Cancel only. Keep both: two rows;
   Cancel: as before. Escape, x and the overlay act as Cancel. [ ]
3. Chain trip keeping and adding. Build 3 legs (unsaved). Market > Option Chain. Tick two contracts, choose Buy or Sell on each, click
   Add Selected. Expect the Builder with 5 rows (your 3 first, then the 2), no question. [ ]
4. Chain trip with a clash. Same, but tick a contract you already hold with the same action. Expect the usual three-button question;
   Cancel adds nothing. Tick the opposite side of a held contract: added silently as a second row. [ ]
5. Leave question. With 3 unsaved legs click Settings (any page but the Option Chain). Expect "Leave the builder? The 3 unsaved legs
   will be lost." Stay / Leave (one leg reads "The 1 unsaved leg will be lost."). Same question from the Option Chain while it holds the legs. [ ]
6. Replace question on a draft link. With legs shown, paste a different `?draft=` link into the address bar of the same tab (or use a link
   from the chain). Expect "Replace the N legs in the builder?" with Replace / Cancel; Cancel keeps the legs and puts the old link back. [ ]
7. Drafts Mode. Open a paper strategy, remove one leg (a pending change), go to the Option Chain and back: the pending change is still
   there. If the book changed meanwhile: "The strategy changed while you were away. Your unsaved edits were not restored." [ ]
New wording to read: the opposite note, the singular "The 1 unsaved leg will be lost.", the Drafts Mode changed-book sentence.

## Review round (26 Nov 2026, overnight): independent reviewer's findings

Tests first: commit `98ad3845`, red run `evidence/lane-b-review-red.txt` (7 failed, 28 passed in the two files). Green after the fix
commits: the same files 35 passed; full vitest 230 files, 2735 passed, 0 skipped. Each claim was confirmed by its red test; none dropped.

| Finding | Verdict | Red to green test | Fix (RCA) |
|---|---|---|---|
| F1 Add Selected merged another underlying | confirmed, FIXED | `chain-trip-adr329.test.js` "F1 held NIFTY legs + ticked SENSEX contracts" | `addFromChain` never compared underlyings; it now adds nothing, keeps the held legs and says "These contracts are on SENSEX; the legs in the builder are on NIFTY. Nothing was added." through the editError path. Owner question OQ-5 filed. |
| F2 second navigation made the older question Leave | confirmed, FIXED | `leave-builder-adr329.test.js` "F2 a second navigation ..." and "F2 a navigation that needs no question ..." | `ask()` called `settle(false)` and `settle(stay)` resolves `!stay`, so the older guard proceeded (Leave); it now settles Stay, as does any newer `allow()`. |
| F3 Back re-ran Add Selected | confirmed, FIXED | `chain-trip-adr329.test.js` "F3 Back from the chain ..." | The hold forgot which `?draft=` it had absorbed; the hold now carries `addedDraft` (set on a successful add, gone with the hold) and the page skips `addFromChain` for the same draft text on the same hold. `?draft=` stays in the URL. |
| F5 stale replace answered after Save | confirmed, FIXED | `chain-trip-adr329.test.js` "F5 the draft query dropped ..." | the `!v` early return ran before `settleReplace`; it now settles the question as Cancel and bumps `replaceSeq`, so a late answer applies nothing and the old link is not written back. |
| F7 dangling promises on unmount | confirmed, FIXED | `leave-builder-adr329.test.js` "F7 unmount ..." and `chain-trip-adr329.test.js` "F7 unmount ..." | neither question was settled when the page went away; `onBeforeUnmount` settles the leave question as Stay (in `useLeaveBuilder`, so the chain page too) and the replace question as Cancel. |

Changed existing test: `builder-hold-adr329.test.js` H2 compares the whole held object; the hold now has the `addedDraft` field (null).
Known edge of F3 (for the owner): a second Add Selected with exactly the same ticks on the same hold produces the same link text and is
skipped; today those ticks would clash with the legs just added and ask, so nothing a trader would want is lost.

### Review findings not fixed
- F4 a cancelled Add Selected leaves `?draft=` in the URL, and a reload then applies it: today's behaviour, unchanged by ADR-329; left as is.
- F6 Drafts Mode unsaved count is `pendingOrders.length`, the number the bar shows (the plan's chosen wording). Listed for the owner's screen check (item 7 and 5 below).

### Screen check added
8. Underlying refusal. Build 3 NIFTY legs (unsaved). Market > Option Chain, switch the chain to SENSEX, tick one contract, Add Selected.
   Expect the Builder with your 3 NIFTY legs unchanged and the sentence "These contracts are on SENSEX; the legs in the builder are on
   NIFTY. Nothing was added." [ ]
9. Back after Add Selected. Add two contracts from the chain, then go to the chain again and press the browser Back: the Builder shows
   the same legs, not the two added again. [ ]
10. Drafts Mode count. In a paper strategy with one pending change, go to any page other than the chain: the question counts the same
    number the bar shows. [ ]
