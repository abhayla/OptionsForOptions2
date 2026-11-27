STATUS 05:40 | 1 F3 dialog half Passed in cloud (paper-cancelled-stops-r2-fa2, 5) | 2 not-live tick Passed in cloud (paper-not-live-tick-r2-fa2, 2) | 3 wording + request key Passed in cloud (paper-exit-request-key-r2-fa2, 2) | 4 leg cost Passed in cloud (paper-stops-leg-cost-r2-fa2, 1) | 5 D2 Passed in cloud (one-date-formatter-d57.r2-1128, 3) | 6 D-12 Passed in cloud (paper-unchecked-confirm-r2-fa2, 2) | 7 #870 Passed in cloud (exit-lock-window-r2-fa2, 3), #872 Passed in cloud (exit-market-reask-r2-fa2, 6), #873 Passed in cloud (3 guards, mutation-checked), #874 already Passed in FA (exit-closed-entry-points-r2-fa, 3) | 8 header Fixed | Opus review: see "Review" | browser check: Not run (see Not done) | next push: at review end | blocker: none

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
5. #870 page side: the page's lock (`exitUnknown`) clears only when a re-read decides; never on a timer. The dialog now says plainly after 120 s that the outcome is not known; nothing else is needed in the page.

## Decided for the owner
1. Cancelled-stop wording is past tense and carries the level: "The stop on <leg> was removed with the move; set a new one on the new leg." (with the level: "The stop on <leg> (level 120.00) was removed with the move; ..."). Basis: ADR-330 (48), the owner's before-the-move sentence "The stop on <leg> will be removed; set a new one after the move."
2. The not-live tick resets on the opening (`props.open`), not on the line's text or the order list. A tick given at 10:41 holds at 10:42. A new opening asks again. Basis: ADR-330 (28), UX-A13/A24.
3. #872 timer: the owner's brief says "ask again while open". The dialog asks again every 15 s only while it is open and holds an exit row (the interval is stopped on close, unmount and an entry-only list). This does not break run-discipline E2: it is not a recurring timer of the session. The timed ask is silent: a failed or unclear answer keeps the last answer and says nothing new. The first ask of an opening and the ask at the Confirm press stay fail-closed (Confirm goes briefly to "checking"; nothing is sent unless the answer is open), because a press is an action and the older tests pin it. Basis: ADR-330 (60), ADR-212.
4. #870: the lock is never cleared by the dialog. After 120 s of `locked` the dialog's unknown-outcome line (`paper-unknown`) says the 120-second sentence instead of the first one, with the same Orderbook button (also when the page's `state` is no longer 'unknown' but the lock stands). Basis: ADR-017 (no unlock on a guess).
5. D-12: when the could-not-check line stands beside a greyed Confirm it ends before "You can still confirm." (a short form). Basis: ADR-330 (60).
6. The request key is a UUID from `crypto.randomUUID()` (a random fallback where it is missing). Basis: the brief, ADR-017.
7. Leg cost: "Costs now <price as the server sent it>" or "Costs now: not priced" (null, empty or absent); the browser forms no money (ADR-008).

## New wording for the owner to read
- "The stop on <leg> (level <level>) was removed with the move; set a new one on the new leg." (the level part is dropped when the reply has none)
- "The stop on the old leg may have been cancelled, and the new leg has no stop until you set one." (the owner's own words from the brief)
- "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known." (replaces "...is being checked; ...until the book has been read.")
- "Two minutes have passed and the outcome of the first exit is still not known. Open the Orderbook to see whether it was placed; no second exit is sent until the answer is known."
- "The app could not check whether this exit leaves a sold option without protection." (the short form, shown when Confirm is off; the full form with "You can still confirm." is unchanged when Confirm is on)
- "Costs now <price>" and "Costs now: not priced" beside each leg's Stop price box.

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
Pending: one Opus review of the whole diff against origin/integration/weekend-1127 (see below once it returns).

## Models and minutes
| task | model | minutes |
|---|---|---|
| items 1 to 8, tests, mutation checks | Sonnet (main) | about 45 |
| review of the whole diff | Opus (reviewer agent) | pending |

## To file as deferred issues
- Positions Exit ticks vanish when prices pause (UX-A01, PaperStrategies.vue).
- Page halves of F3, `client_request_id` and the leg cost (see "For the owner lane" 1 to 3).
