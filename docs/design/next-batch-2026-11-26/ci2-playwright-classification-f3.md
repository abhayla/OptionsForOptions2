# CI-2: classification of the failing Playwright tests (Lane F3, 28 Nov 2026 IST)

How it was run: the frontend job's Playwright step as CI runs it (read from `.github/workflows/app-tests.yml`: `npx playwright test`, `CI=1`, projects mobile-390 and desktop-1280, `REPLAY_URL` on a preview whose API proxy points at a closed port), here on the head of fix/r3-frontend-f3-1128 (build a1d70422 + FJ2 f23 + Lane F3's changes), the 8 `screen-*.spec.ts` files: 1674 test runs, 1476 passed, 2 skipped, **196 failed = 98 distinct tests x 2 projects**. Coordinator's count was 75 on a1d70422: the extra ones here come from decisions that landed after (FJ2 f23: My Strategies text, one failed-load state; Lane F3: dated times). positions.spec.ts, index-view.spec.ts, my-strategies.spec.ts need the real API in CI and are NOT in this table yet (second table, to follow).

Classes: (a) expected-fail by design, (b) stale spec (the screen changed by a decision), (c) environment, (d) real product defect.
**(a): none.** No failing test carries `test.fail()`; the 13 `test.fail()` tests of the suite all fail as expected and count as passed. **(c): none found.** **(d): none found so far**; the C9 rows are not yet pinned and are listed honestly as unknown.

## Causes
| Id | Class | Cause | Evidence | Fix |
|---|---|---|---|---|
| C1 | (b) | Alerts model changed by ADR-330 (3), (4): one server read GET /alerts/active (+ /alerts/answered), answered rows, no "Earlier" and no mark-read; the spec stubs GET /api/paper/alerts and POST /api/paper/alerts/read, which the app no longer calls (the stub answers 503, so the page shows nothing / a dash) | src/lib/paperAlerts.js lines 1-10, 37, 75; e2e stub screen-alerts.spec.ts lines 80-88 | rewrite the stub to the real routes and the expectations to the answered model |
| C2 | (b) | One failed-load state for every list page (Lane FC2 I-86, FJ2 T3-10): the neutral failure is ONE sentence with a Retry button (ListLoadFailed / LoadFailed, ids `<prefix>-error` / `<prefix>-retry`); the spec expects the old four-part neutral block (`<prefix>-what`) and no button | src/components/common/ListLoadFailed.vue header; src/lib/listFailed.js | update the expected text and ids; assert the Retry button and one click re-reads |
| C3 | (b) | The Exit dialog asks GET /api/market/exit-state (ADR-330 (60)); the spec stub does not answer it (503), so the dialog fails closed with Confirm off (MARKET_UNREADABLE_TEXT) | src/components/strategy/PaperConfirmDialog.vue askMarket(); e2e stub has no /api/market/exit-state | add the market-open answer to the stub (and a closed case that asserts the sentence) |
| C4 | (b) | A failed read no longer greys Exit; Exit opens the dialog, which says why and keeps Confirm off (owner order on PC O-A-12, FJ group B 7d0310e49; ADR-330 (60)); the spec expects a disabled Exit and the old error ids | src/components/strategy/PaperStrategies.vue ExitButton :blocked; tests/exit-greyed-no-dialog-r3-fj.test.js | change the expectations to: enabled, click opens the dialog with the not-live line, Confirm off |
| C5 | (b) | A time that is not today shows its date (F3 MUST of 28 Nov 22:15, istStamp): the per-leg price time and the paused reason now carry the date and "as of" (FJ2-1) | src/components/strategy/PaperStrategies.vue paper-ltp-at; src/lib/paperList.js withAsOf | expect the dated form (the spec date 26 Nov is not today) |
| C6 | (b) | The Live card is quiet when the page notice speaks (UX-A09, ADR-330 (56)): the stub answers GET /api/market/indices with state NOT_CONNECTED, so the page notice is up and the card hides its own checked-at / paused line | src/components/live/LiveStrategyCard.vue line 239 (!quiet); e2e/support/live-card-stub.ts line 141 | give the stub a live index answer for the card tests; keep one test for the quiet case |
| C7 | (b) | My Strategies wording and counts moved by decision: the empty state names where Completed strategies are (T2-17, FJ2 f23) and "Select all N of M shown" counts the filtered rows | src/pages/MyStrategiesPage.vue | update the expected text |
| C8 | (b) | Settings landing moved (FJ group B 7d0310e49: /settings lands on app-settings) | FJ RESULTS group B | update the expected address |
| C9 | (?) | Cause not yet pinned down; first read below, to be confirmed in the fix pass |  |  |

## Counts (distinct tests)
C1: 24; C2: 28; C3: 17; C4: 5; C5: 2; C6: 8; C7: 3; C8: 1; C9: 10; total 98

## Every failing test
| spec | test | cause | what it checks | projects failing |
|---|---|---|---|---|
| screen-alerts | ACT-1 | C1 | absent: no alerts -> the empty state with the exact line, no list, nothing marked read | 2 |
| screen-alerts | ACT-2 | C1 | two unread stops: listed as the server sent them (newest first) with title, IST time, stra | 2 |
| screen-alerts | ACT-3 | C1 | only an already-read stop: it sits under "Earlier", nothing is on top, nothing is sent, th | 2 |
| screen-alerts | ACT-4 | C1 | an open adjustment record and one unread stop: the open record is first, the list length e | 2 |
| screen-alerts | ACT-5 | C1 | the open record shows the trade, its time and the rule's words, and "Compare approaches" o | 2 |
| screen-alerts | ACT-6 | C1 | a strategy with no name is shown as "Strategy <id>", on a stop and on an open record | 2 |
| screen-alerts | ACT-7 | C1 | a body that begins with the title repeats nothing: the title shows once (U23) | 2 |
| screen-alerts | ACT-8 | C1 | a body that does not begin with the title is shown whole | 2 |
| screen-alerts | ACT-9 | C1 | failed read (500 with the catalogue message): the four parts exactly, no rows, no empty li | 2 |
| screen-alerts | ACT-10 | C1 | not found (404 with the catalogue message): shown the same way, nothing else | 2 |
| screen-alerts | ACT-11 | C1 | connection refused: the neutral four-part message, no rows, no guessed number | 2 |
| screen-alerts | ACT-12 | C1 | a 500 whose body is not a catalogue message (a framework detail) shows the neutral message | 2 |
| screen-alerts | ACT-13 | C1 | ambiguous answer (a negative unread count) is treated as a failed read: neutral message, n | 2 |
| screen-alerts | ACT-14 | C1 | ambiguous answer (a row with no created_at) is treated as a failed read: neutral message,  | 2 |
| screen-alerts | ACT-15 | C1 | the mark-read POST fails (500): the stops stay on top as unread, no error is shown, the be | 2 |
| screen-alerts | ACT-16 | C1 | the open records cannot be read (500): the stops still list and the bell counts only the s | 2 |
| screen-alerts | HIST-2 | C1 | absent: no records -> the empty state with the exact line | 2 |
| screen-alerts | HIST-5 | C2 | connection refused: the neutral four-part message, no rows, no empty line | 2 |
| screen-alerts | HIST-6 | C2 | ambiguous answer (one record with no time) is a failed read: neutral message, not the good | 2 |
| screen-alerts | HIST-8 | C1 | History lists the records answer only: a stop in the unread list is not listed here unless | 2 |
| screen-builder-legs | PP-4 | C3 | Review and add opens the confirm list: title, one Exit row for the removed leg, the not-re | 2 |
| screen-builder-legs | PP-7 | C3 | Confirm posts exactly one order: the removed leg's opposite side, its whole quantity, kind | 2 |
| screen-builder-legs | PP-8 | C3 | after Confirm the position is read again; when that read fails the list says "Placed on pa | 2 |
| screen-builder-legs | PP-9 | C3 | a refused order (422) shows the server's sentence in the list, keeps Confirm, and nothing  | 2 |
| screen-builder-legs | PP-10 | C3 | N-01 the refusal line in the list does not vanish by itself | 2 |
| screen-builder-legs | PP-11 | C3 | an answer that does not arrive in a state we know (5xx): "We could not confirm the order.  | 2 |
| screen-builder-legs | PP-22 | C4 | N-04 the page closes the Exit list only when the trade changed elsewhere (with a sentence) | 2 |
| screen-home | BELL-1 | C1 | with 3 unread the bell says "Alerts, 3 unread", shows 3, and opens Alerts > Active | 2 |
| screen-home | BELL-4 | C1 | the badge adds the open adjustment records to the unread stops (2 + 1 = 3) | 2 |
| screen-home | ACCT-3 | C8 | the "Account & Settings" title link opens the settings section (its first built page) | 2 |
| screen-home | STATE-2 | C1 | absent: no saved strategies -> the new-user Home, exact text, no recent list, figures 0 /  | 2 |
| screen-home | FAIL-1 | C2 | API 500 with a catalogue message: the server's four parts, the running count is "—" with " | 2 |
| screen-home | FAIL-2 | C2 | API 500 with no catalogue body: the neutral four-part message, never the server's own word | 2 |
| screen-home | FAIL-3 | C2 | not found: GET /strategies answers 404 -> the same neutral message, no state guessed | 2 |
| screen-home | FAIL-4 | C2 | network down (connection refused): the neutral message, "Create Strategy" is NOT offered a | 2 |
| screen-home | FAIL-5 | C2 | ambiguous: 200 with an unreadable body (no strategies list) -> error state, not "no strate | 2 |
| screen-home | FIG-1 | C1 | stated: running = rows whose server word is Running (2 of 4), unread = the bell number, to | 2 |
| screen-home | FIG-3 | C1 | zero: a total of +0.00 is shown as the server wrote it (not a dash), and running / unread  | 2 |
| screen-home | FIG-5 | C1 | read failed: paper list 500 -> total "—" with "Paper P&L is not available right now.", the | 2 |
| screen-home | STRIP-3 | C9 | not connected: the strip says "Index values unavailable." and each value reads "Not availa | 2 |
| screen-live-strategies | FAIL-1 | C2 | list 500 with a catalogue message: the server's four parts, no card, no empty text | 2 |
| screen-live-strategies | FAIL-2 | C2 | list 500 with no catalogue body: the neutral four-part message, never the server's own wor | 2 |
| screen-live-strategies | FAIL-3 | C2 | connection refused: the neutral message; the page does not claim "No saved strategies yet" | 2 |
| screen-live-strategies | FAIL-4 | C2 | not found (404): the neutral message, no state guessed | 2 |
| screen-live-strategies | FAIL-5 | C2 | unreadable body (200 with text that is not JSON): the neutral message, never a blank page  | 2 |
| screen-live-strategies | FAIL-6 | C2 | unreadable body (200 with a JSON object that has no strategies list): the neutral message | 2 |
| screen-live-strategies | CARD-1 | C6 | a Running card: title, status word, checked-at, spot with its time, breakevens, max profit | 2 |
| screen-live-strategies | CARD-8 | C6 | market closed: ONE banner for the screen with the price's own time, no per-card "at <time> | 2 |
| screen-live-strategies | ST-10 | C6 | a Running trade whose open legs are on expired contracts (D-40): the server's own sentence | 2 |
| screen-live-strategies | SOCK-6 | C6 | a later push moves the numbers: the card shows the new LTP and the new "Checked at" time | 2 |
| screen-live-strategies | LINK-5 | C6 | Stops on a Running card opens Current positions on the Paper filter for that strategy (LIV | 2 |
| screen-live-strategies | LINK-6 | C6 | Exit on a Running card opens Current positions on the Paper filter and the paper exit conf | 2 |
| screen-live-strategies | LINK-6b | C6 | Exit on a strategy with no open paper legs: the Positions page says "This strategy has no  | 2 |
| screen-live-strategies | LINK-7 | C2 | Exit and Stops are placed on no order button: the card has no order, execute or exit-in-pl | 2 |
| screen-live-strategies | LINK-11 | C6 | N-14: two paper trades saved under the same name can be told apart on their cards | 2 |
| screen-live-strategies | OPP-5 | C9 | the reason list holds "-" and the server's four reasons; Dismiss with a reason posts it fo | 2 |
| screen-live-strategies | OPP-13 | C2 | inbox 500 without a catalogue body, and connection refused: the neutral parts | 2 |
| screen-live-strategies | OPP-14 | C2 | connection refused on the inbox: the neutral parts | 2 |
| screen-live-strategies | OPP-15 | C2 | unreadable inbox body (200, not JSON): the neutral parts, never "No adjustment opportuniti | 2 |
| screen-live-strategies | ADJ-17 | C2 | failures: the type list 500 shows the server's sentence; connection refused shows the neut | 2 |
| screen-live-strategies | ADJ-18 | C2 | connection refused on the type list: "Something went wrong. Please try again.", no editor | 2 |
| screen-my-strategies | EMPTY-2 | C7 | a list that holds only Completed strategies is empty here too; the Completed page says "No | 2 |
| screen-my-strategies | DEL-17 | C2 | when the revision cannot be read no DELETE is sent (fail closed) and the neutral message s | 2 |
| screen-my-strategies | BULK-2 | C7 | (MYSTR-02) "Select all 3 shown" counts only the rows that can be deleted (held and basket- | 2 |
| screen-my-strategies | BULK-14 | C9 | a revision that cannot be read: that row is kept as failed with "The strategy could not be | 2 |
| screen-my-strategies | BULK-15 | C9 | every revision unreadable: nothing is sent to bulk-delete and every row is named as kept | 2 |
| screen-my-strategies | BULK-24 | C7 | when no row can be deleted "Select all 0 shown" is greyed | 2 |
| screen-positions | TOT-12 | C5 | a refresh that fails with a list on screen pauses every figure and keeps the cards | 2 |
| screen-positions | REAL-10 | C2 | no broker connection: the catalogue refusal, no rows, no empty state, and the paper list s | 2 |
| screen-positions | REAL-12 | C2 | connection refused on the read: the neutral four-part message, no number, no empty-state w | 2 |
| screen-positions | REAL-13 | C2 | an unreadable broker status after a refused read is a failed read (fail closed) | 2 |
| screen-positions | REAL-14 | C2 | an unreadable positions body (no strategies list) shows the failure message, not a blank o | 2 |
| screen-positions | REAL-15 | C2 | the real section has no order button of any kind (every action routes back to the strategy | 2 |
| screen-positions | PAP-5 | C2 | connection refused on the paper read: the neutral four-part message and no card | 2 |
| screen-positions | PAP-6 | C2 | an unreadable paper body (no strategies list) is the neutral message, no card, no figure | 2 |
| screen-positions | PAP-8 | C5 | a card shows the legs: side, name, lots, average, price and the time of that price | 2 |
| screen-positions | PAP-21 | C2 | a failed re-read keeps the cards but pauses the figures with the failure message above the | 2 |
| screen-positions | EXIT-3 | C3 | Exit (1) opens "Exit Paper positions" with the one ticked leg: side, "Exit", name, lots, t | 2 |
| screen-positions | EXIT-10 | C3 | Confirm posts ONE order: the opposite side, whole lots x lot size, kind exit, no price fro | 2 |
| screen-positions | EXIT-11 | C3 | a partial exit: Lots can be lowered, and the order carries lots x lot size | 2 |
| screen-positions | EXIT-13 | C3 | an exit that leaves a sold option unprotected shows the server's warning line; Confirm sta | 2 |
| screen-positions | EXIT-14 | C3 | when the protection check cannot run the dialog says so (never "no risk") and Confirm stay | 2 |
| screen-positions | EXIT-16 | C3 | a refused exit (4xx) stays in the dialog with the server's text and Confirm greyed until t | 2 |
| screen-positions | EXIT-17 | C3 | a failed exit (500 or connection refused) says the outcome is unknown, offers Open Orderbo | 2 |
| screen-positions | EXIT-17b | C3 | "Open Orderbook" closes the dialog and opens the strategy's builder where its book is | 2 |
| screen-positions | EXIT-17c | C3 | after the 5 second hold on an unknown outcome Confirm unlocks (the user has had time to ch | 2 |
| screen-positions | EXIT-18 | C3 | a stored exit followed by a failed re-read: the dialog closes, an error banner shows, the  | 2 |
| screen-positions | EXIT-19 | C4 | while the last read failed, Exit is disabled with "Prices are not live; try again when the | 2 |
| screen-positions | EXIT-20 | C4 | a disabled (blocked) Exit button looks disabled, not like a usable one (owner N-05) | 2 |
| screen-positions | EXIT-21 | C4 | a failed re-read while the dialog is open keeps it open, blocked, with the leg and the not | 2 |
| screen-positions | EXIT-26 | C4 | ?exit= after a failed first read opens nothing and does not come back on the next good rea | 2 |
| screen-positions | STOP-7 | C9 | a valid Above level enables Save, posts the level as typed, says "Saved: exit above 25700" | 2 |
| screen-positions | STOP-8 | C9 | Below alone and Above plus Below together post the right body and say both in one line | 2 |
| screen-positions | STOP-9 | C9 | saving a level that is already armed says "Already set: ..." and stores nothing new | 2 |
| screen-positions | STOP-13 | C9 | a save with the connection refused gives the same line, and Save works again afterwards | 2 |
| screen-positions | STOP-22 | C9 | a stop typed in one leg's box does not move into another leg's box, and typing never jumps | 2 |
| screen-positions | STOP-32 | C9 | every control of the panel is reachable with the keyboard: Tab from Above reaches Below, t | 2 |
| screen-positions | KEY-2 | C3 | Enter on the focused Confirm posts the exit once (keyboard parity with the click) | 2 |

## Result (Lane F3, 29 Nov 00:20 IST): every row above fixed to the decided behaviour, none skipped
Run as CI runs it (`CI=1 npx playwright test`, retries 1, both projects, 4 workers) on this head: the 8 `screen-*.spec.ts` files = **1652 passed, 0 failed, 2 skipped (as before), 20 flaky** (the 20 are mobile-390 tests that passed on the retry; they passed first time in the single-file runs: the run shared the CPU with my other runs). The three files that need the real API (`positions.spec.ts`, `index-view.spec.ts`, `my-strategies.spec.ts`), run against a local API and database as CI does: 14 passed, 2 skipped (the Save Draft tests need the seeded catalogue), 0 failed. Before the fixes the first two had 2 + 1 failing tests (x2 projects); the single failing `my-strategies.spec.ts` test CI reported was not reproducible here (it passes), so it is listed as "not reproduced".

### The ten that were not pinned (C9), now classified
| spec | test | class | cause |
|---|---|---|---|
| screen-home | STRIP-3 | (b) | ADR-330 (56) round 2 (b4c5ec832): with an answer in hand the page's ONE price notice speaks; the strip does not repeat "Index values unavailable." |
| screen-live-strategies | ST-10 | (b) | Lane Y item 1 (080afd10a): the worker's monitoring answer owns the paused badge (shared MonitoringBadge); the card's local badge steps aside |
| screen-live-strategies | LINK-6b | (b) | the Running row must carry `position_kind: 'paper'` (ADR-330 (64)) to show its Exit link; the spec fixture lacked it |
| screen-live-strategies | OPP-5 | (b) | Lane F3's own I-201: a dismissal with no reason says "No reason given" |
| screen-live-strategies | ADJ-17, ADJ-18 | (b) | D-TD-2 / I-86 (Lane FC2 cd3a22875): Retry beside the server's sentence; one failed-load sentence with no server message |
| screen-live-strategies | LINK-7 | (b) | ADR-330 (54): the Plan button of a running trade is the card's one button; it places no order |
| screen-my-strategies | DEL-17, BULK-14, BULK-15 | (b) | N-30: a delete sends the revision the LIST ROW carries (no read per row); the spec made the per-row read fail while the row had a revision. Fail-closed kept and now tested the right way: a row with no revision and an unreadable strategy sends nothing |
| screen-positions | STOP-22 | (c) | the measure was in viewport coordinates: filling a box scrolls the page by 7 px (the Stops panel moved 7 px as a whole; the leg box and its reason slot kept their offsets inside it). No layout jump; the spec now measures inside the panel |
| screen-positions | EXIT-17c | (b) | Lane U r1 (ADR-016/017/019): after an unknown outcome Confirm waits for the page's re-read, never a timer (stricter than the 5 s hold of the old spec) |

### Product change found by this work (mine, fixed)
My own earlier item 3 (I-207) had made Positions, not connected, print only the first sentence of a clean server message: REAL-10 showed the next-action text was lost. Now a refusal whose four parts all read as sentences keeps them with a Retry (REQ-065, D-TD-2); only a raw (JSON or class-code) or missing message becomes the one plain sentence. Files: PositionsPage.vue and its tests.

### Found, not assigned
- Builder book panel (PaperBookPanel.vue, Lane F1b): Exit all and each leg's Exit are greyed while a read has failed (D-05), where ADR-330 (60) says the Exit control opens its dialog and the dialog gives the reason. On Positions the two already agree. Written as a question in RESULTS-lane-f3.md.
- The CI "frontend" job: with all specs green the Playwright step is about 9 minutes here on 4 workers; the CI runner has 2 workers (playwright.config.ts), so expect about 15 to 18 minutes for Playwright on top of the unit tests; the 40-minute limit Lane T set is needed.
