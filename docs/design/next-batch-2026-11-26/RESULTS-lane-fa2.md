STATUS 06:05 | 1 F3 dialog half Passed in cloud (paper-cancelled-stops-r2-fa2, 5) | 2 not-live tick Passed in cloud (paper-not-live-tick-r2-fa2, 2) | 3 wording + request key Passed in cloud (paper-exit-request-key-r2-fa2, 2) | 4 leg cost Passed in cloud (paper-stops-leg-cost-r2-fa2, 1) | 5 D2 Passed in cloud (one-date-formatter-d57.r2-1128, 3) | 6 D-12 Passed in cloud (paper-unchecked-confirm-r2-fa2, 2) | 7 #870 Passed in cloud (exit-lock-window-r2-fa2, 3), #872 Passed in cloud (exit-market-reask-r2-fa2, 6), #873 Passed in cloud (3 guards, mutation-checked), #874 already Passed in FA (exit-closed-entry-points-r2-fa, 3) | 8 header Fixed | Opus review REVISE then fixed (see Review) | browser check: Not run (see Not done) | pushed 339f014 | gate TOTAL PASS (prepush --jobs 2, proxy vars unset, after pip install of the dev requirements and git fetch --unshallow) | blocker: none

STATUS+ coordinator items (07:30 message): A Add to Paper after the close Passed in cloud (paper-entry-closed-r2-fa2, 3; 12 older tests re-mocked or inverted) | B level format Passed in cloud (paper-stops-level-format-r2-fa2, 9; paper-stops.test.js pins updated) | C #870 page half: dialog prop `lockedAtMs` built, Passed in cloud (exit-lock-window-r2-fa2, 4); page wiring under For the owner lane 5 | full vitest 3831 of 3831 | gate: see the end of this file

# Lane FA2: Exit dialog and stops panel, second batch
Branch fix/r2-exit-stops-2-1128 from origin/fix/r2-exit-stops-1128 (5884a9b). Paper only. Spec basis: ADR-330 (48), (49), (56), (58), (60); ADR-017; ADR-212; REQ-049.
Every item: failing test seen red first, then the fix, then green (counts below are the green runs).

| Item | State | Evidence (npx vitest run, this lane) |
|---|---|---|
| 1 F3 dialog half: one line per cancelled stop from the reply alone | Passed in cloud (dialog half). The page half is NOT built: see "For the owner lane" 1 | tests/paper-cancelled-stops-r2-fa2.test.js: red 3 failed / 2 passed (the two "nothing shown" cases pass trivially), green 5 of 5. States: list present (2 lines, level), list empty, field absent (null), entry without leg name (falls back to contract text, junk entries skipped), follow-up reads all failing (api mock rejects every get/post: lines still show), reply unreadable (the may-have-been-cancelled sentence) |
| 2 not-live tick must reset only when the OPENING changes | Passed in cloud | tests/paper-not-live-tick-r2-fa2.test.js: red 1 failed / 1 passed, green 2 of 2 (the minute changes while open: tick and Confirm stay; close and reopen un-ticks) |
| 3 EXIT_CHECKING_TEXT true in the 120 s window; `client_request_id` | Passed in cloud (dialog half). The post is in a file outside my list: see "For the owner lane" 2 | tests/paper-exit-request-key-r2-fa2.test.js: red 2 failed, green 2 of 2; tests/exit-unknown-resend-adr017.test.js 8 of 8 (its pinned sentence updated) |
| 4 UX-A02 what the leg costs now beside the Stop price box | Passed in cloud (panel half). The parent must pass the price: see "For the owner lane" 3 | tests/paper-stops-leg-cost-r2-fa2.test.js: red 1 failed, green 1 of 1; paper-stops.test.js and paper-stops-leg-risk-w2b.test.js still green (53 of 53 with the new one) |
| 5 D2 stop row date | Passed in cloud. Finding: the fix was already in the base (Lane FA r2, `serverLegText`); the `it.fails` case of Lane TB is now a plain `it` and passes without a code change | tests/one-date-formatter-d57.r2-1128.test.js 3 of 3 (copied from origin/test/r2-frontend-1128, the one `it.fails` turned into `it`) |
| 6 D-12 "You can still confirm" only when Confirm is enabled | Passed in cloud | tests/paper-unchecked-confirm-r2-fa2.test.js: red 1 failed, green 2 of 2; tests/paper-exit-warning.test.js 9 of 9 still green |
| 7a #870 lock after all re-reads fail | Passed in cloud (dialog half; the lock itself stays until the page's re-read decides) | tests/exit-lock-window-r2-fa2.test.js: red 3 failed, green 3 of 3 (119 s: first sentence; 120 s: the 120-second sentence + the Orderbook button, Confirm still off after 10 more minutes; lock cleared by the re-read: line gone) |
| 7b #872 ask again while open | Passed in cloud | tests/exit-market-reask-r2-fa2.test.js: red 4 failed / 2 passed, green 6 of 6; older #872 / ADR-330 (60) tests still green (24 of 24 with the new file) |
| 7c #873 three guards | Passed in cloud, each mutation-checked | stale answer: removing `if (seq !== marketSeq) return` fails "stale answer" (1 failed); re-ask on new orders: removing `askMarket()` from the opening watch fails 5; page-close clearing of the waiting change: deleting `exitAllWaiting.value = null` in cancelPaperDialog (StrategyBuilderPage.vue line 609, reverted at once, file untouched) failed the new tests/exit-page-close-waiting-r2-fa2.test.js (1 failed); the old tests passed with the line deleted (26 of 26), so none covered it |
| 7d #874 Positions market-closed test | Passed in cloud in Lane FA (not repeated) | tests/exit-closed-entry-points-r2-fa.test.js 3 of 3 (Positions Exit with a ticked leg: dialog, line, Confirm greyed, nothing posted; the open-market twin proves it is not vacuous) |
| 8 paper-exit-warning.test.js header | Fixed | the header now says Confirm is locked while the check runs (hotfix 27 Nov) |

## For the owner lane
1. F3 page half (StrategyBuilderPage.vue, Lane FB2; the dialog is built and waits for it). In `confirmPending`, on the 201 reply: read `data.cancelled_stops` and pass it to the dialog: `<PaperConfirmDialog ... :cancelled-stops="cancelledStops" :stops-reply-unreadable="stopsReplyUnreadable" />` with `cancelledStops = ref(null)` set to `Array.isArray(data?.cancelled_stops) ? data.cancelled_stops : null`, and `stopsReplyUnreadable = ref(true)` when a 2xx reply is not an object (cannot be read). Reset both to null / false when a dialog opens. The dialog shows one line per entry whatever the follow-up reads do. Keep the existing offer ("Set a stop on <new leg>", tests/paper-move-stop-offer-774.test.js): it rests on the follow-up reads; the lines no longer do. Because a successful exit closes the dialog, also show the same lines from `cancelledStopLines(cancelledStops)` (lib/tracking.js) inside the page's `stop-offer` block, so they stay on screen after the dialog closes. Entry shape: `{leg, contract, level}`; the dialog also accepts `contract_text`.
2. Request key (item 3). The dialog now emits `confirm(orders, held, ticked, requestKey)`; `requestKey` is a UUID made at each Confirm press. `confirmPending` (StrategyBuilderPage.vue), the Positions confirm handler (PaperStrategies.vue) and AlertsPage.vue must send it as `client_request_id` in the body of the order post (or `Idempotency` header if FD2 chose that: read FD2's route), and a re-send of the same Confirm (the page's retry after an unknown outcome) must send the SAME key; a new Confirm press gets the new key the dialog gives. Never make a key in the page.
3. Leg cost (item 4). PaperStrategies.vue `stopLegs` (line 316): add `ltpText: p.ltpText` to each leg object (a live leg gives the text, others null; `not priced` shows). The builder's offer (`stopOffer.legs`) can pass `ltpText` the same way from the book.
4. UX-A01 ticks vanishing when prices pause lives in PaperStrategies.vue (Positions): the Exit ticks must not be cleared when the price state changes; clear them only when the set of open legs changes. The dialog-side half (the not-live tick) is item 2.
5. #870 page side (coordinator item C). The dialog already says the 120-second sentence whenever it gets `locked`; the two pages that own a lock must pass WHEN the unknown reply came, so the window counts from the reply and not from a reopening:
   - StrategyBuilderPage.vue (Lane FB2), line 1495 `<PaperConfirmDialog ...>`: add `:locked-at-ms="exitUnknown ? exitUnknown.at : 0"` (`exitUnknown.at` is already `Date.now()` at the reply, line 701). Also decide whether `EARLY_MS = 5000` (line 793) may stay: it unlocks after 5 s when a re-read shows the book unchanged; if the server's commit window is 120 s that is a guess under ADR-017 (see Review).
   - PaperStrategies.vue (Lane FC2), line 169: add `:locked-at-ms="confirm && isUnknown(confirm.id) ? (unresolved[confirm.id]?.at ?? 0) : 0"`, and store `at: Date.now()` in the `unresolved[strategyId]` record where a POST ends unknown (line 334 comment names the record `{ names, units, seq }`: add `at`). Both pages keep `:locked` as it is; the lock still clears only when a good re-read that started after the reply decides it, never on a timer.
   - AlertsPage.vue (Lane FC2) shows the same dialog for its strategy: if it keeps its own unknown record, pass `:locked` and `:locked-at-ms` the same way.

## Decided for the owner
0. (item A) ADR-330 (60) is applied to Add to Paper: the entry dialog asks the same server answer (GET /api/market/exit-state), shows its sentence, greys Confirm, fails closed on an unreadable or ambiguous answer, re-asks every 15 s while open and at the Confirm press. Basis: ADR-330 (60), ADR-212, ADR-017 (nothing is sent on a closed or unclear answer). Gap: the server's sentence reads "The market is closed. Exits can be placed from 09:15 on <day>." because the route was built for exits; for an entry dialog the word "Exits" is wrong. Lane FD2 should serve an entries wording (or one neutral sentence) from the same route; the browser shows the server's text unchanged (it never rewrites a server sentence). Real case: Sunday 29 Nov, Add to Paper on the builder: before, an empty price box, no tick box and a refusal from the route.
0b. (item B) the Stops panel's Saved lines print the level through `levelShown` ("Saved: exit above 24,500.00"), the form the list shows; the typed text is regrouped as text, no number is read (ADR-008). Basis: the coordinator's item.
1. Cancelled-stop wording is past tense and carries the level: "The stop on <leg> was removed with the move; set a new one on the new leg." (with the level: "The stop on <leg> (level 120.00) was removed with the move; ..."). Basis: ADR-330 (48), the owner's before-the-move sentence "The stop on <leg> will be removed; set a new one after the move."
2. The not-live tick resets on the opening (`props.open`), not on the line's text or the order list. A tick given at 10:41 holds at 10:42. A new opening asks again. Basis: ADR-330 (28), UX-A13/A24.
3. #872 timer: the owner's brief says "ask again while open". The dialog asks again every 15 s only while it is open and holds an exit row (the interval is stopped on close, unmount and an entry-only list). This does not break run-discipline E2: it is not a recurring timer of the session. The timed ask is silent: a failed or unclear answer keeps the last answer and says nothing new. The first ask of an opening and the ask at the Confirm press stay fail-closed (Confirm goes briefly to "checking"; nothing is sent unless the answer is open), because a press is an action and the older tests pin it. Basis: ADR-330 (60), ADR-212.
4. #870: the lock is never cleared by the dialog. After 120 s of `locked` the dialog's unknown-outcome line (`paper-unknown`) says the 120-second sentence instead of the first one, with the same Orderbook button (also when the page's `state` is no longer 'unknown' but the lock stands). Basis: ADR-017 (no unlock on a guess).
5. D-12: when the could-not-check line stands beside a greyed Confirm it ends before "You can still confirm." (a short form). Basis: ADR-330 (60).
6. The request key is a UUID from `crypto.randomUUID()` (a random fallback where it is missing). Basis: the brief, ADR-017.
7. Leg cost: "Costs now <price as the server sent it>" or "Costs now: not priced" (the leg's `ltpText` is null or empty); a parent that passes no `ltpText` field gets no line at all (review S4: otherwise every live leg would read "not priced" until the parent change lands); the browser forms no money (ADR-008).

## New wording for the owner to read
- "The stop on <leg> (level <level>) was removed with the move; set a new one on the new leg." (the level part is dropped when the reply has none)
- "The stop on the old leg may have been cancelled, and the new leg has no stop until you set one." (the owner's own words from the brief)
- "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known." (replaces "...is being checked; ...until the book has been read.")
- "Two minutes have passed and the outcome of the first exit is still not known. Open the Orderbook to see whether it was placed; no second exit is sent until the answer is known."
- "The app could not check whether this exit leaves a sold option without protection." (the short form, shown when Confirm is off; the full form with "You can still confirm." is unchanged when Confirm is on)
- "Costs now <price>" and "Costs now: not priced" beside each leg's Stop price box.

## Coordinator items (message 07:30 IST)
| Item | State | Evidence |
|---|---|---|
| A Add to Paper after the close (board I-147, D-4): dialog opens with its legs, says the server's closed sentence, Confirm greyed | Passed in cloud | tests/paper-entry-closed-r2-fa2.test.js: red 2 failed / 1 passed, green 3 of 3 (closed: leg listed, sentence, Confirm off, click emits nothing; open: one confirm; unreadable and ambiguous: Confirm off). The dialog asks the one market-state answer for ANY row list now (first ask, 15 s re-ask, Confirm press), not only exits. 12 older tests had to change: 10 files whose API mocks lacked `GET /market/exit-state` now answer open, 2 tests that said "an entry-only dialog never asks" now say it asks (exit-market-closed-adr330-60, exit-market-recheck-r2-fa); 3 dialog-level tests got a `flushPromises()` before the Confirm click. Full `npx vitest run`: 3831 of 3831 |
| B PaperStops level format (TD O-6) | Passed in cloud | tests/paper-stops-level-format-r2-fa2.test.js 9 of 9 (`levelShown`, lib/tracking.js, on displayFormat's `groupedIndian`: 24000 -> 24,000.00; 24000.05 -> 24,000.05; 120 -> 120.00; not a plain decimal: as typed). The Saved / Already set lines of the Stops panel use it; tests/paper-stops.test.js and stops-index-closed-r2-fa.test.js pins updated to the new forms (72 of 72). Red step: the helper did not exist, so the first run could only fail on import; not run separately |
| C #870 page half | Dialog side Passed in cloud; page wiring is "For the owner lane" 5 | new prop `lockedAtMs` (when the unknown reply came); tests/exit-lock-window-r2-fa2.test.js 4 of 4 (red 1 failed): reply 100 s ago, dialog opened now: the 120-second sentence shows 20 s later; a reply 500 s ago: at once |

## Not done
- The page halves in "For the owner lane" 1 to 3 (files of other lanes).
- The browser check with Chromium against `vite preview` and screenshots under docs/design/next-batch-2026-11-26/screens-fa2/: not run. The pages need the API (the Exit dialog needs the book, the market state and the risk reads); the cloud has no server for them and a mocked browser run would show the mock, not the app. PC steps below cover it.

## PC steps
Market closed (any time outside 09:15 to 15:30 IST, e.g. Sunday):
1. Positions: tick a leg and press Exit. The dialog lists the leg and shows the server's sentence "The market is closed. Exits can be placed from 09:15 on <next trading day>."; Confirm is greyed. If the risk line says "The app could not check ...", it must NOT say "You can still confirm."
2. Open Stops on a strategy: each leg row shows "Costs now <price>" or "Costs now: not priced" beside the Stop price box (needs the owner-lane change 3).
3. Leave the dialog open across 09:15: within 15 s Confirm turns on without reopening (needs a live open; skip on a Sunday).

Live market:
4. Positions with prices pausing every 60 s (UX-A13): open the Exit dialog on a not-live price, tick "I understand ...", wait for the next price pause: the tick stays and Confirm stays on.
5. Move a leg's expiry in the builder, Confirm: one line per cancelled stop appears (needs the owner-lane change 1 and FD2's `cancelled_stops`); switch the network off just after Confirm: the lines (or the "may have been cancelled" sentence) still show.
6. Make an exit whose answer times out (FD2's test mode): Confirm stays off; after two minutes the dialog says the outcome is not known and offers the Orderbook.

## Review
Opus (reviewer agent, whole diff against origin/integration/weekend-1127, includes FA's I-17, I-18, I-29): REVISE, no blocker. Fixed in this push:
| Finding | Result |
|---|---|
| S1 the timed re-ask ("closed") hid the unknown-outcome line and its Orderbook button | Fixed: the unknown/locked line sits above the market line. Test: exit-market-reask-r2-fa2 "review S1" |
| S2 test "closing stops the asking" could not fail | Fixed: asserts `vi.getTimerCount()` is 0 |
| S3 test "a new lock starts a new window" could not fail | Fixed: advances the second 120 s and expects the sentence |
| S4 "Costs now: not priced" on every live leg (parents pass no price) | Fixed: no line unless the parent passes the field (Decided 7) |
| S5 age line stale while open | Fixed: the 15 s tick refreshes the age clock |
| S6 request key made and dropped; comment said a page sends it | Comment corrected; page half is "For the owner lane" 2; to file |
| N1 stuck grey, no line, when a timed ask fails while the first ask hangs | Fixed: it turns the market state unreadable (line shown). Test "review N1" |
| N2 tick holds across a new order list in one opening | Not changed (Decided 2; entry dialogs only) |
| N3 stale comment in PaperStops (last close) and "last close shown" in the leg-stop-only offer with no close | Not changed; listed |
| N4 "no second exit is sent" holds per page, not per strategy (each page has its own exit record) | Not changed; to file |
Outside the diff (to file): the builder's `decideUnknownExit` (StrategyBuilderPage.vue:793, `EARLY_MS = 5000`) says "not stored, you can try again" and unlocks after 5 s when a re-read shows the book unchanged. If the server's commit window really is 120 s that unlock is a guess (ADR-017) and the 120 s figure needs checking with Lane FD2. A new press carries a new key, so a forwarded key would not stop that duplicate either.
Not covered by the review: backend routes, SaveDraftBar held-basket path with the key, I-18 scroll, AlertsPage, any browser walk-through. A quote under 1 s in the future reads "0 seconds ago" (priceAgeLine, not changed).

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 to 8, tests, mutation checks | Sonnet (main) | about 45 |
| review of the whole diff | Opus (reviewer agent) | 7 |

## To file as deferred issues
- Builder 5 s unlock after an unknown outcome vs a 120 s commit window (ADR-017); confirm the window with FD2.
- A request key must also cover a new press after an unknown outcome (server-side idempotency design).
- Exit record is per page, not per strategy (N4).
- Positions Exit ticks vanish when prices pause (UX-A01, PaperStrategies.vue).
- Page halves of F3, `client_request_id` and the leg cost (see "For the owner lane" 1 to 3).


## Gate for the second push
The coordinator items A, B, C (a delta of about 20 files, mostly test mocks) were NOT part of the Opus review above; the one review covered the diff up to 1c2dad5. A short Opus review of that delta is recommended before the owner relies on item A (it changes when the entry Confirm is enabled).

SAFE TO CLOSE (see the STATUS line for the head; left: the page halves in "For the owner lane" 1, 2, 3, 5, the entries wording from FD2, the browser check, the deferred issues above)
