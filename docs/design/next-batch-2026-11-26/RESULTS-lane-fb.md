STATUS 05:10 | F1 fixed c076af20c (pushed, gate TOTAL PASS --jobs 2) | UX-A03 proven already, UX-B25 fixed, UX-AF1 fixed, UX-C3 fixed (PlanWatch line for the owner lane) | item 1 I-30 Fixed not tested (cloud: passed) | item 2 I-49 cause found, page half proven, fix is for the owner lane | item 3 I-50 Fixed not tested (cloud: passed) | item 4 I-68 no code change, one-press proven already holds | next push: this one | blocker: none

# Lane FB round 2: Builder page (branch fix/r2-builder-1128, from integration/conflicts-1127 16c536f0)

Paper only. No broker order endpoint was called. Files edited: `StrategyBuilderPage.vue`, `LegList.vue`, `sharedStateText.js`, five new test files, this file, `screens-fb/`.

## Status per item
| item | state | evidence (cloud, this session) |
|---|---|---|
| 1 I-30 contract-list line | Passed in cloud (tests/contract-list-line-r2-fb.test.js, 5 tests). Browser: screens-fb/01-contract-list-line.png | red 2 of 5 before the fix, 5 of 5 after |
| 2 I-49 slow first prices | Cause found. Page half proven by test (tests/builder-first-prices-r2-fb.test.js, 2 tests). The fix is in files this lane may not edit: see "For the owner lane" | passes: it records the order |
| 3 I-50 one loading state per leg | Passed in cloud (tests/leg-working-r2-fb.test.js, 7 tests). Browser: screens-fb/02-leg-working.png | red 3 of 6 before the fix, 7 of 7 after |
| 4b I-68 review F2 (page path) and F3 | Fixed, passed in cloud (tests/add-to-paper-r2-fb.test.js, 4 tests): F2 test was RED before the fix (2 posts, expected 1), green after; F3 test written with the fix, not run red | see Item 4b |
| 4 I-68 Add to Paper one press | NO CODE CHANGE: the one-press, one-order rule already holds. Guard test added (tests/add-to-paper-r2-fb.test.js, 2 tests, green on the unchanged code; it could not be run red) | see "Item 4" |

Highest status claimed: Fixed, not tested on the owner's PC (market closed, no live feed here).

## Item 1 (I-30)
- Cause: `list_notice` was returned by `GET /catalogue/<underlying>/expiries` and read nowhere (grep of `frontend/src` was empty).
- Fix: the page reads the expiries reply for the underlying it shows (header underlying, else the picker's) and shows the server's own line in one paragraph (`data-testid="contract-list-notice"`) above the leg list, also when the list is empty and says "No legs yet". Nothing is worded in the browser. The line is read again every 60 s while it shows, so it goes by itself when a reply carries none (about 08:35); no timer runs once it is gone.
- Test states: present; absent (null); empty text; expiries call failed; line goes on a later reply; a failed re-read keeps the last known line (it says nothing new).
- Decided for the owner (spec basis ADR-330 (61): "the line stays until today's list is in use"): a failed read neither shows an invented line nor removes one already shown, because removing it would claim today's list is in use.
- Gap listed: the same line is NOT shown on the Option Chain, Create Strategy and Execute pages (only the builder was in the queue). `/health` also carries `instrument_list` and `instrument_list_day` but no sentence; not used.

## Item 2 (I-49)
- Finding, with the order recorded by test: after a pick the leg reaches the page only after `POST /strategies/planned-entry` has been answered. The outcome request (`POST /strategies/outcome`) and the leg-edit read are sent in the same tick as the page receives the leg, and neither waits for the other (page half, proven). So the first prices wait twice: the planned-entry reply, then the outcome reply. T2-11 (14 s) is those two waits added; the page's own request order is not the cause.
- Why the page cannot send the outcome earlier: `buildDraft` needs a planned entry on every leg (ADR-075), so the outcome request cannot go before the capture.

## Item 3 (I-50)
- Cause: a leg row shows its price box and a caption ("<time> IST" or "Your price, <time>") that read as a figure while the outcome was still being worked out; no per-leg working state existed.
- Fix: `LegList.vue` takes a `working` prop (the page passes `updating`: the newest outcome or leg-edit request has no reply). While it is on, each priced, included leg shows one line `Working out the outcome...` (shared constant `LEG_WORKING_TEXT`, also used by the opening card), in the space the caption already reserves, so no row moves. A leg that is left out, has its own `block` text, or whose typed price was refused shows its own line instead. The user's typed text stays in the price box (their own input is never hidden); only the outcome words are held back. The real caption returns when the reply arrives.
- Test: three legs, slow outcome mock (never answers), same words on all three, no capture time; one leg refused: its own text, the other two the loading word; request failed: no loading word; reply arrived: caption and typed line back.

## Item 4 (I-68)
- Cause (read from the code, then proven with a slow-post test on the real page): there is no swallowed first press and no double submit. The two "presses" are two decided steps: (a) Add to Paper on an UNSAVED strategy opens the name dialog first (ADR-330 (19)); (b) while prices are not live (a slow outcome makes them so) the confirm list carries the line to tick and Confirm is greyed until it is ticked (ADR-330 (28)). Confirm also greys while the post runs (`busy`) and after a refusal until the user edits something (REQ-163).
- One press, one order: proven on the real page with a slow post: one Confirm -> 1 post; two more presses while it runs -> still 1; after release -> 1. A refused post followed by an edit -> exactly 1 more post (2 in all).
- Not changed because both steps are spec decisions the owner made; changing them needs the owner (see Decided for the owner and "For the owner lane").
- Real-order twin: the builder has no real-order "Add to Paper" twin; real orders are placed on the Execute page, which is not in this lane's files. Gap: the Execute page's single-press rule was not checked here.
- Opus review of item 4: REVISE, see "Review" below (it found real double-order and greyed-Confirm causes; item 4 is therefore NOT closed).

## Item 4b (Opus review F2 page path, F3), `StrategyBuilderPage.vue`
- F2: an ADD-only post with no answer now sets a page lock (`addUnknown`); "Review and add" is refused with `ADD_UNKNOWN_TEXT` until a book read shows the net changed (the add was stored) or the book is left and reopened. Exits keep their own lock. Fail-closed.
- F3: the stops read before the post is inside a try, and after it the page re-checks that the book and dialog are still open and not blocked; otherwise nothing is posted and `paperBusy` is freed.
- Not fixed (other lanes' files, For the owner lane): F1, F2 save-bar path, F4.

## Item 0 (Lane Z review F1: unknown exit unlocked by a 5 s timer), `StrategyBuilderPage.vue`, `sharedStateText.js`
- Before: `decideUnknownExit` said "not stored" and unlocked Exit when the book looked unchanged 5 s after the client gave up; the server can still commit later (no idempotency key), so a second partial Exit could commit too (2 of 4 lots twice = 4 lots).
- Now: an UNCHANGED book decides "not stored" only on a read taken more than `UNKNOWN_EXIT_WINDOW_MS` = 120 s after the client gave up (worst case 30 s pool wait x 2 checkouts + 30 s row lock = 90 s, plus 30 s margin); a book that MOVED decides at once; meanwhile Exit stays locked with the existing plain line. The automatic re-read runs every 5 s until the window has passed.
- Opus review of this change: REVISE, all page-side points fixed: F1 the lock now names its strategy and only a read of that strategy's book decides it (another strategy opened + its Orderbook link no longer unlocks; other strategies are not locked); F2 window 70 s -> 120 s (the reviewer showed 90 s worst case); F4 an older answer no longer ends the re-read loop for good.
- Tests: tests/exit-unknown-window-r2-fb.test.js (5 tests; the 2-of-4-lots core, the window, F1 other-strategy, F4, window size): red on the old code, green now; tests/exit-unknown-resend-adr017.test.js timings moved from 5 s to the window (11 + 2 pass).
- Still open (cannot be fixed on the page): see For the owner lane 3 to 6.

## Notes of the 27 Nov PC test (coordinator queue)
| id | state | what |
|---|---|---|
| UX-A03 | proven already | A fired leg stop carries no "If this stop fires..." line: `paper_monitor.py` `_max_loss_line` returns None for a leg stop; `tests_app/test_stop_fired_message.py` (asserts the line is absent, line 68) is on the build, and `frontend/tests/paper-stops-leg-risk-w2b.test.js` passes here (15). No such sentence is built in `frontend/src`. The database test could NOT be run in this container (no PostgreSQL); proven by code read plus the frontend run only. |
| UX-B25 | fixed, not tested on the PC | The whole-trade tiles (Profit left, Max profit, Loss left, charges) took the book's figures even while an exit's outcome was unknown for this book, so they kept the old book's numbers and then jumped. Now, while the lock for THIS book is on, `paperLeft` and the paper charges are off and the screen legs' own outcome speaks; they return when the server decides. Test: tests/builder-ux-r2-fb.test.js (red before: tiles stayed, green after). Only the unknown-exit lock is covered; a book read that failed or a not-live lock still shows the last good book (said by its own lines): the exact T2-08 reproduction was not possible without live data. |
| UX-AF1 | fixed, not tested on the PC | Cause: the banner took the index's last tick (15:35:41) while the answer was out and the server's close sentence (15:30:00) after it. Now `closedBannerFor` (sharedStateText.js): while an answer is out the banner keeps the last settled one, with none settled it says only "Market closed." (no time that may change). Tests: 3 on the helper (the page's market-closed state cannot be reached in the cloud test clock). |
| UX-C3 | fixed (two of three lines) | With nothing to mark (no old numbers) the legs card no longer adds "Updating the numbers..." beside the page's "Working out the outcome..." and the per-leg words (`oneLine`). The third line, "Plan watch: Loading the rule check...", comes from `PlanWatch.vue` (not this lane's file): see For the owner lane 7. |

## Decided for the owner
0. I-68 F2: fail-closed lock after an unknown add (ADR-016..019); the user reopens the strategy to clear it.
1. I-30: a failed re-read keeps the line already shown (ADR-330 (61)).
2. I-68: no change. Both extra steps are decided: (19) the name step and (28) the tick. If the owner wants one press, that is a SPEC CHANGE to ADR-330 (19) (name asked after the trade, not before) and (28) (the tick folded into Confirm); not done while the owner sleeps.
3. I-50: the loading words equal the opening card's (`Working out the outcome...`).

## pending owner read (new on-screen sentences)
- `The last paper order got no answer and may be stored. It is not sent again until the Paper book has been read: open the strategy again to check.` (Review and add after an unknown add)
- UX-AF1: none new ("Market closed." is the existing no-time sentence).
- `Working out the outcome...` shown on each leg row (same words as the existing opening card).
- The contract-list line is the server's template `contract_list_earlier` ("Contract list of <date>. Today's list loads at about <hh:mm>."), not new here. Example shown in the screenshot: "Contract list of 26 Nov. Today's list loads at about 08:35."

## For the owner lane
1. I-49, `frontend/src/components/strategy/LegPicker.vue` (not this lane's file): `save()` (about line 555, `await capture(id, und)` before `emit('update:legs', ...)`) and `addChosen()` (about line 618, `await Promise.all(chosen.map(capture))` before `emit('update:legs', ...)`) hold the leg back until the planned-entry reply. Two ways to cut the first wait, both needing an owner or backend call: (a) start `capture()` when the B/S cell is picked (before Done) so the reply is already there at Done; (b) backend (Lane FD): make `POST /strategies/planned-entry` answer from the first tick without waiting for the subscribe round trip, and let the outcome take the live price when the leg has none. I did not pick one: (a) changes when a price is captured (the captured time shown to the user).
2. I-68 review: F1 `PaperConfirmDialog.vue:124` should reset the tick when the OPENING changes, not when the line's "as of HH:MM" text changes; F2 save bar `SaveDraftBar.vue:355,372-380`: keep a per-strategy unknown lock that `canAddToPaper` checks and `openPaperDialog` does not reset; F4: keep `refusedAt` across reopen. If the owner decides one press: `SaveDraftBar.vue` `startPaper()` (name step) and `PaperConfirmDialog.vue` `canConfirm` (`props.notLiveLine && !notLiveAck`).

3. UNKNOWN exits, the real fix is on the server (`routes/paper.py`, Lane FD): an idempotency key on `POST /paper/strategies/{id}/orders` (request field `client_request_id`, a UUID the page makes per Confirm and re-sends only as the SAME key; the server stores it with the orders and answers a repeat with the stored result) or a deadline the server checks before commit so the 120 s window becomes a real limit. The page's timer is a guess.
4. The unknown lock lives only in the page: leaving the page, a reload, or the Positions page exit (`PaperStrategies.vue`, its own `exitRec`) drop it, so a second exit can be sent inside the window. Needs the lock stored server-side (a pending-order record) or the key above.
5. `usePaperExit.js` `EXIT_CHECKING_TEXT` ends "...until the book has been read": no longer true inside the window; suggested words: "The first exit's outcome is not known yet; no second exit is sent until the server's answer is known." (Lane FA file; pending owner read).
7. UX-C3: `PlanWatch.vue` `LOADING_TEXT` should not show while the builder's outcome is loading (hide it, or the page passes a prop that says so).
6. SaveDraftBar / the same unknown lock for ADDS exists on the page (ADD lock, item 4b) but not in the save-bar path.

## To file as deferred issues
- Each automatic re-read of an unknown exit calls `enterDrafts` (`openSaved`): with the longer loop it pulls the page back to the locked strategy and resets an edited leg (reviewer runs A6, A7) while the lock lasts.
- Contract-list line on Option Chain, Create Strategy and Execute pages.
- Execute page: check the single-press rule of the real order path.

## Process notes
No override of the pre-push check was set or attempted; no `.claude/`, `tools/` or workflow file edited. The first gate runs failed on the container (Python packages and `origin/main` missing, then a 15 s load timeout of Lane FC's scan test at 4 jobs); fixed by installing the project's requirements, fetching `origin/main`, and running `--jobs 2`.

## Review (Opus, item 4): REVISE
One press -> one POST: confirmed (not found otherwise). Swallowed first press: not found. But:
- F1 (greyed Confirm, likely the owner's cause): `PaperConfirmDialog.vue:124` clears the not-live tick whenever the line text changes; the text carries "as of HH:MM" (from `priceAsOf` / oldest capture), so a new minute un-ticks the box and greys Confirm while the dialog is open. FILE: PaperConfirmDialog.vue = Lane FA, see For the owner lane.
- F2 (CRITICAL, two-press double order): after an unknown outcome (5xx/timeout) Cancel then Add to Paper re-opens with state READY and Confirm enabled; the second POST is stored (no idempotency key; `paper.py:1383-1395` checks only inside one request), lots double. Save-bar path: `SaveDraftBar.vue:355,372-380` (not this lane's file, For the owner lane). Page path (Review and add, add-only orders): `StrategyBuilderPage.vue` sets the `exitUnknown` lock only when the orders include an exit: fixed here, see item 4b.
- F3 (page): `paper.value.net` read after `await readStops(id)` outside the try; a route change during that GET leaves `paperBusy` true and the dialog stuck. Fixed here, see item 4b.
- F4 (minor): a 422 refusal's "edit before resend" rule does not survive Cancel and reopen (nothing stored, no double order). For the owner lane.
Real-order twin: none in the builder; `ExecuteStrategyPage.vue` prepare() was not checked for a double basket after a 5xx.

## Tasks / model / minutes
| task | model | minutes |
|---|---|---|
| items 1 to 4: tests, fixes, browser checks | Sonnet (this session) | about 25 |
| Opus review of item 4 | Opus | about 4 |

## PC steps
Market closed (any time):
1. `git fetch && git checkout fix/r2-builder-1128`, start the app, open the builder with no legs. If the instrument list is yesterday's (before the load), expect the server's line above the legs. Run `cd frontend && npx vitest run tests/contract-list-line-r2-fb.test.js tests/leg-working-r2-fb.test.js tests/builder-first-prices-r2-fb.test.js tests/add-to-paper-r2-fb.test.js`.
2. Pick two legs: while the outcome is out, every leg row says `Working out the outcome...` and shows no capture time; the figures return when it answers.
Live (market open):
1. Between 08:30 and about 08:35: the line `Contract list of <yesterday>. Today's list loads at about 08:35.` shows on the builder, also with no legs; within about a minute after the list loads it disappears with no reload.
2. Pick one leg from the strike table and time Done to first prices; compare with 14 s (T2-11). Expect the same (this lane did not change it).
3. Add to Paper on a new strategy: the name step, then the list. With live prices Confirm is not greyed; press Confirm twice quickly: one paper order only.

SAFE TO CLOSE (head: see the last commit of fix/r2-builder-1128; left: item 2 fix in LegPicker/backend and the owner decision on I-68; Opus review done: F1, F2 save-bar path, F4 for the owner lane)
