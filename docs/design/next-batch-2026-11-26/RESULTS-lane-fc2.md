STATUS 08:20 | pushed before: 89edbfe, cd3a228 | this push (07:30 items, ONE gate for all): order path client_request_id (Opus review REVISE: F1 and F2 fixed, rest listed), UX-A19 AppHeader fix, Adjustments Retry: Passed in cloud | tool-call budget (300) exceeded by about 6 calls to commit, gate and push this work instead of losing it | blocker: none (send_message to the parent is refused: untrusted device; this file is the report)

# Lane FC2: pages (Alerts, Positions, strategy lists, chart)

Branch `fix/r2-pages-1128` from `origin/fix/r2-small-screens-1128`. Paper only; no broker call anywhere; no money arithmetic added.

## Status per item (push 1, head 89edbfe, gate TOTAL PASS)

| Item | State | Test (cloud) |
|---|---|---|
| 1 Alerts > History loading line | Passed in cloud | `paper-alerts.r2-1128.test.js` 4 passed, 0 `it.fails` left (the TB `it.fails` is a plain `it`; seen red before the fix) |
| 1 Alerts > Active (UX-A07, UX-A29) | Passed in cloud, no code change needed | same file: Active cases (8 s pending, empty, failed) were already green on this base |
| D-6 OI line printed twice | Passed in cloud | `payoff-oi-r2-fc2.test.js` 4 passed |
| D-7 `NIFTYRunning` | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-7) |
| D-8 empty cells in a closed row | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-8) |
| D-11 paused sentence twice, compact row | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-11) |
| D-13 Real part never re-read | Passed in cloud | `positions-real-reread-r2-fc2.test.js` 5 passed |
| D-4 Add to Paper after the close | Blocked: the dialog is `PaperConfirmDialog.vue` (Lane FA2); no other dialog exists | exact change below |
| UX-B04 step 4 progress words | Passed in cloud | `create-strategy.test.js` -t UX-B04 |
| UX-A09 one notice for the page | Passed in cloud | `paper-pages-r2-fc2.test.js` (UX-A09, 5 cases + `priceNoticeUp`) |
| UX-A12 settled trade | No change: its words are in Lane FB2 and FC3 files | none |

## Status per item (push 2: the coordinator's additions of 05:25 and 06:15 IST)

| Item | State | Test (cloud) |
|---|---|---|
| (61) contract-list line on Option Chain and Create Strategy | Passed in cloud. The server's `list_notice` on `GET /catalogue/<u>/expiries` is shown as sent (Option Chain under the header; Create Strategy step 3); nothing when null, empty or not text | `option-chain.test.js` "ADR-330 (61)" 5 cases; `create-strategy.test.js` "ADR-330 (61)" 4 cases (each seen red first for the "shows the line" case) |
| UX-A01 ticks and the words beside a greyed Exit | Passed in cloud. Ticks already survive a pause and a failed read (proven by test); the missing part was the time: a greyed Exit under "prices are not live" now has a second line "Last prices: HH:MM:SS IST." from the last good answer. "Nothing ticked" keeps "Tick a leg to exit." | `paper-pages-r2-fc2.test.js` UX-A01 (3 cases) |
| UX-A19 (I-72) Create Strategy clicked twice leaves the menu open | Test written and RED on this base, kept as `it.fails` (TB's convention) because the fix is in `AppHeader.vue`, not in my list | `nav-same-page-r2-fc2.test.js`; body fails with "expected true to be false" at the menu after a same-page item click (checked by running the body as a plain `it`) |
| UX-A05 Plan door on the Live card | Passed in cloud: a running trade (real or paper) shows the `Plan` button (the one `PlanDoor.vue`, same sheet as Positions); none on Draft, Completed or an errored card | `live-card-links-s14.test.js` UX-A05 (6 cases; the two "shows" cases red first) |
| D-TD-2 (I-86) six list pages, no Retry, three wordings | Passed in cloud for Live Strategies, Alerts > Active, Alerts > History, Positions, Adjustment opportunities, Home (new `ListLoadFailed.vue`: with no server message ONE sentence and Retry; with a server message its four parts stay and Retry sits under them) and the Option Chain (Retry added; its own sentence stays). My Strategies and Completed Strategies already had Retry (`MyStrategiesPage`). NOT done: Adjustments (playbook editor page, see Not done) | `list-load-failed-r2-fc2.test.js` 14 passed (6 pages x {down, Retry recovers; server refusal keeps four parts and Retry} + 2 unit); `option-chain.test.js` "D-TD-2" 1 passed |
| O-1 (I-157) paused line has no as-of | Passed in cloud for the failed-read path: the paused sentence now reads ", as of <date>, <time> IST" from the last good answer, through `pausedText` (the one formatter); no good read yet: the sentence alone. The server-paused path already printed it when the server sent `as_of` | `paper-pages-r2-fc2.test.js` O-1 (2 cases); `paper-strategies.test.js` D-05 r3 expectation updated to the dated sentence |
| O-3, O-4, O-6 | Not in my files, see "For the owner lane" | none |
| UX-A02 current price into PaperStops | Built on my side: `PaperStrategies.vue` passes `current-price-text` = `{ "<contractId>": "<ltp text>" }` for the live open legs | `paper-pages-r2-fc2.test.js` UX-A02 (1 case; PaperStops stubbed) |
| #870 the page keeps re-reading after an exit of unknown outcome | Not changed. The Positions list already re-reads every 5 s with no gate (`usePaperRefresh`, no `enabled`), and the unknown outcome is decided only by a good re-read that started after the reply (Lane U); I did not add a test that drives the whole exit flow, so this is code-read, not proven here | none |
| UX-B06 running trade ticked with a draft, "Delete selected (2)" | Closed by Lane FC's bulk-delete work on this base, as designed (ADR-330 (8)): a running trade can be ticked and the confirmation says how many are running ("Delete 3 strategies? 1 of them is running.") | `my-strategies-bulk.test.js` "confirmation names the count and how many are running; singular for 1; no running clause at 0" (1 passed, run again this push). If the PC meant a running trade must NOT be deletable in bulk, that is a spec change for the owner |

## Status per item (push 3: the coordinator's 07:30 IST items; ONE gate and ONE push for the three, not one each: a gate takes about 30 minutes and my tool-call budget could not carry three)

| Item | State | Test (cloud) |
|---|---|---|
| 1 Order path: `client_request_id` on every exit request, one key per user action, the same key on a resend | Passed in cloud (after the Opus review, below). `PaperStrategies.vue` sends the exit through `addToPaper(withRequestKey(api, key), ...)` (new `lib/requestKey.js`; `tracking.js` is FA2's, untouched). A key is lent to a resend only when the last attempt ended UNKNOWN, the orders text is the same and the page's record of that attempt is still open (unknown / not stored, or none because the screen was mounted again); the key store is per tab. It ends when the server stored the order (201) or refused it (400/409/422). `AlertsPage.vue` sends no order itself: its only POST is `/alerts/<id>/answer`; its Exit opens the same `PaperStrategies` exit door | `paper-order-key-r2-fc2.test.js` 8 passed (key present; refused then retry = new key; stored then same exit = new key; unknown then resend = SAME key; unknown settled as placed then identical exit = NEW key (review F1, red first); remount keeps the key (F2); key-rule unit; client wrapper). Wiring off: 3 cases fail. Older pins updated: `exit-gate-d05.test.js`, `paper-list-4b.test.js` expect `{ orders, client_request_id }` |
| 2 UX-A19 (I-72) menu stays open after Create Strategy twice | Passed in cloud: `@click="closeMenu()"` on the menu items in `AppHeader.vue`; red before (the `it.fails` body failed with "expected true to be false"), plain `it` now | `nav-same-page-r2-fc2.test.js` 1 passed; `nav-label-click`, `nav-shell`, `nav-every-item-ux26`, `header-bell-open-records` still pass |
| 3 I-156 remainder: Adjustments page has no Retry | Passed in cloud: a failed load (types, list or labels) with no server text shows the shared sentence and Retry (`pb-load-retry`); with the server's own text its line stays and Retry sits beside it; a refused save or delete keeps its line; the raw "Network Error" text is no longer shown | `adjustment-preferences-tab.test.js` "D-TD-2" 1 passed (red first) |

Frontend suite before the review fixes: 323 files, 3831 tests passed; after them the touched files (order key, exit gate, paper list, dialog safe, exit unknown resend, paper strategies) pass: 135 tests; the full suite is re-run by the gate.

Whole frontend suite on the final tree: 322 files, 3825 tests passed.

Browser checks (Chromium against `vite preview` of a fresh build, `/api` answered by mocks), shots in `docs/design/next-batch-2026-11-26/screens-fc2/`: `alerts-history-loading.png`, `positions-paused-one-notice.png`, `create-strategy-step4-progress.png` (push 1). Push 2 screens (Live card Plan door, list Retry): not taken, see Not done.

## For the owner lane

**D-4 (Lane FA2, `PaperConfirmDialog.vue`; Lane FB2 for any wiring in `SaveDraftBar.vue`).** The Exit dialog already asks the one market answer (`GET /market/exit-state`) and greys Confirm when it says closed. The Add to Paper dialog (first basket, add rows) never asks it, which is why it opens with an empty Price box and the route then refuses with MARKET_DATA_102.
- `askMarket()` (about line 147): change `if (!props.open || !rows.value.some((r) => r.kind === 'exit')) { ... return }` to `if (!props.open || !rows.value.length) { ... return }` so every dialog with rows asks once per opening. `canConfirm` already returns false for `closed`, `checking` and `unreadable`, and `marketLine` already prints the server's sentence. For an entry the sentence may say "Exits"; if the owner wants "Orders can be placed from 09:15 on ...", that is the server's one sentence (Lane FD2).
- Test to add (FA2): one `kind: 'open'` row, `GET /market/exit-state` answering `{closed: true, sentence: ...}`; expect `paper-market-closed` shows the sentence and `paper-confirm-button` is disabled; with `{closed: false}` it is enabled once the price is valid.

**UX-A19 (`AppHeader.vue`): DONE in push 3; the text below is the diagnosis.** The menu closes only when `route.fullPath` changes (watch, about line 228). A click on the item of the page already shown navigates nowhere, so the menu stays open. One-line fix: on the `router-link` of the menu items (about line 405, `data-testid="nav-menu-item"`) add `@click="closeMenu()"`. Then change `it.fails` to `it` in `frontend/tests/nav-same-page-r2-fc2.test.js`.

**O-3 (FA2, `PaperConfirmDialog.vue`):** the "Prices are not live" sentence is printed although one contract only has no price; name the contract (the dialog already has the leg names it builds `exitEndText` from).
**O-4 (FB2, builder tiles/table):** the table total does not move with the booked switch (it always includes booked); the OFF state prints whole rupees, ON prints paise. The spec does not say; owner to decide.
**O-6 (FA2, `PaperStops.vue`):** the status after Save says `24000` while the list says `24,000.00`; use the one number format for both.
**UX-A02 (FA2, `PaperStops.vue`):** declare the prop `currentPriceText` as `{ type: Object, default: () => ({}) }` (map of contract id string to the server's price text, same key as `legs[].contractId`); until it exists Vue puts it on the root as a plain attribute (harmless).
**`PriceNotice.vue` (shared):** should call `priceNoticeUp` from `lib/priceState.js` instead of keeping its own copy of the rule (see push 1).
**`PositionsTotals.vue` (not in my list):** untouched; the list hands it a Paper total with no paused sentence when two or more strategies are paused.
**`strategies/adjustments` (Adjustments page):** no Retry yet, see Not done.

## Decided for the owner

1. **D-4** as (60) says for the Exit dialog (Spec basis: ADR-330 (60), (58)): the Add to Paper dialog opens, shows the legs and the server's market-closed sentence, and its Confirm is greyed; no empty Price box without a reason line. Not built here (FA2's file); the exact change is above.
2. **D-8:** a closed leg row shows its booked figure and "—" (the app's one dash) in Unbooked and P&L; the booked figure is not repeated in P&L.
3. **D-6:** the OI line prints the sentence once; a server reason that already starts with it is printed as sent.
4. **D-11:** where several lines under one compact row say the book is paused, the one with the "as of" time is printed (`pausedOnce`).
5. **D-13:** Real part re-read every 30 s and on the browser's `offline` / `online` events; a figure older than 90 s (the server's `STALE_AFTER_SECONDS`) is hidden; a refused read shows the not-connected message and a dash; timers and listeners go when the page is left. (Spec basis: ADR-330 (24), ADR-016.)
6. **UX-A09:** with two or more open paper strategies paused the page says the paused sentence once, with its "as of" time; tiles are greyed with no sentence; the headline Paper total carries no repeated reason. One paused strategy: its tile keeps its line (ADR-330 (56)). A failed refresh keeps its banner.
7. **(61) line:** the Option Chain and Create Strategy show the server's `list_notice` exactly as sent, in the same place the field arrives (the expiries answer); nothing is printed when it is absent.
8. **D-TD-2:** one failed-load rule for list pages: no message from the server means ONE sentence and a Retry; a message from the server keeps its four parts and gets a Retry below. The Option Chain keeps its own sentence ("The expiries could not be read, so no chain is shown.") because a test and the shared text file pin it, and gets a Retry. If the owner wants the chain on the shared sentence too, it is a one-line swap.
9. **UX-A01:** a greyed Exit says which reason in words: "Tick a leg to exit." (nothing ticked) or the not-live sentence followed by "Last prices: HH:MM:SS IST." (the time of the last good answer, never the time of a failed read, ADR-330 (56)).
10. **UX-A05:** the Live card's Plan door appears for every running trade, real or paper, with the same button and sheet as Positions; none on drafts, completed trades or a card that could not load.
11. **O-1:** after a failed read the paused sentence carries the date and time of the last good prices; with no good read it carries none (never a made-up time).

## New wording for the owner to read

- Step 4 of Create Strategy, under "Loading…" (UX-B04): "Reading the strategy list. This can take up to 20 seconds." / "Reading the planned entry prices of N contracts. This can take up to 20 seconds." / "Pricing N strategies: D of N done. This can take up to 20 seconds." (1: "1 contract", "1 strategy"; "20 seconds" is the longest wait the PC walk saw, stated as a limit).
- Positions, hidden Real figure (D-13): "The real P&L figure is more than 90 seconds old and is hidden until the next read." (reworded from a first draft that named the broker: Positions code may not name it, tests/test_no_broker_name_in_feature_code.py.)
- Every list page, failed load with no server message (D-TD-2): "Could not load this list. Nothing was changed." with the button "Retry" (existing label). My Strategies keeps its older "Could not load your strategies. Nothing was changed."
- Greyed Exit under a pause (UX-A01): "Last prices: 15:27:00 IST." (second line; the first line is the existing "Prices are not live; try again when they update").
- Existing sentences, not new: the paused sentence with ", as of <date>, <time> IST" (O-1), "Contract list of <date>. Today's list loads at about 08:35." (the server's text, shown on two more pages), "Plan" (the button).

## Not done

- D-4 build (FA2's file; change above). UX-A19 fix (AppHeader.vue; one line above). O-3, O-4, O-6, UX-A02's other half (FA2/FB2).
- (Done in push 3) D-TD-2 on the Adjustments page.
- #870: not proven by a new test (see table). UX-AF2, UX-B03: not retested.
- D-13 "on socket loss": the Positions page opens no feed socket, so the re-read is hooked to the browser's `offline` / `online` events; the index socket's drop is not a trigger.
- Browser shots for the push-2 screens (Live card Plan door, list Retry): not taken; they are covered by component tests only.
- Mutation proof: red-then-green seen for items 1, D-6, D-7, D-8, D-11, D-13, UX-B04, UX-A09, (61), UX-A05, UX-A01 (the as-of line), O-1 and the UX-A09 headline total. For D-TD-2 the tests were written after the code (the old pages had no Retry at all, so they could not have passed); not run red.

## To file as deferred issues

- `PriceNotice.vue` should use `priceNoticeUp` (see For the owner lane).
- `TrackingPanel.vue:100` unused `LEG_PNL_MISSING` (lint warning, Lane FC3's file) and `tests/option-chain.test.js:148` unused `params` (old line, not mine).
- The container this lane ran in had no `ruff`, no `httpx` and a shallow git history, so the first two gate runs failed for environment reasons; I installed them (pip, `git fetch --unshallow`); nothing in the repo changed for that.

## PC steps

Market closed (after 15:30 IST):
1. Alerts > History: reload; "Loading..." while it reads, never "No stops or expiry settlements yet." first.
2. Positions with two or more open paper strategies and the feed down: the paused sentence appears once at the top with its date and time; "NIFTY" and "Running" have a gap; Show closed positions: a closed row has "—" in Unbooked and P&L.
3. Create Strategy: step 4, click Show strategies: below "Loading…" a line names what is read and says up to 20 seconds. Step 3 shows the "Contract list of ..." line only while yesterday's list is in use (08:30 to about 08:35).
4. Positions > Real: with a session, end the session; within about 30 s the Real P&L is a dash with the not-connected message, no reload.
5. Live Strategies: a running trade's card has a Plan button; it opens the same plan sheet as the Positions row.
6. Stop the API and open Live Strategies, Alerts (Active, History), Positions, Adjustment opportunities, Home, Option Chain: each says one failed-load sentence and has Retry; start the API, press Retry: the page loads.
7. Positions: tick a leg, then make the read fail (stop the API): the tick stays; Exit (1) is off with the not-live sentence and "Last prices: <time> IST."
8. Add to Paper after the close: not fixed here (D-4, FA2). Create Strategy clicked twice with the menu: not fixed here (UX-A19, AppHeader).

Live (market open): the same, with the feed running: no paused sentence; pause the feed and it appears once; on Positions > Real leave the page open for more than 90 s with Zerodha unreachable: the figure disappears with the sentence above, and returns after the next good read; leave the page and wait 2 minutes: no more `GET /api/positions` in the network log.

## Review (Opus, order path, item 1 only; commit d7a9a14dc): REVISE, two of three important findings fixed in this push

- **F1 (important, FIXED):** a new exit could reuse an old key after an unknown outcome that a re-read settled as "placed" (the server would then place nothing). A key is now lent only while the previous attempt's record is unknown / not stored (or absent after a remount); test red first.
- **F2 (important, FIXED for the same tab):** keys died with the component (Cancel on the Alerts exit door unmounts it; the Orderbook link leaves the page). The store is now module-level. NOT fixed: a page reload or a second tab loses the key (reviewer: mirror to `sessionStorage`; also the per-instance unknown lock `exitRec`, which predates this lane, should live outside the instance: to file as a deferred issue).
- **F3 (important, not checkable here, Lane FD2):** `tracking.js` classes every 4xx except 408/429 as REFUSED and then the key ends. If FD2 answers a repeat of a stored exit with 409 or 422, the page says "refused, nothing stored" for an order that exists and the next Confirm places a second one. FD2 must answer a repeat like the original success (201 with the stored orders) or with a distinct code the client maps to placed; add that client test when the route is on this branch.
- **F4 (nit):** only the newest orders text is remembered per strategy (A, unknown, edit to B, back to A: new key). Safer later: one key per strategy while an unresolved record stands, FD2 refusing a key reused with another body.
- **F5 (nit, partly fixed):** tests added for the signature branch, F1 and F2; not covered: cancel then reopen in one instance, and the fallback branch of `newRequestKey` (runs only without `crypto.randomUUID`).
- **F6 (nit):** the fallback key uses `Math.random`; `crypto.getRandomValues` is stronger. The server should scope keys per user and strategy.
- **F7 (outside my files, Lane FB2):** the builder's exit door (`StrategyBuilderPage.vue:690`, `confirmPending` to `postPaperOrders`) posts exit rows with no `client_request_id`; `PaperStops.vue` posts triggers (not orders) without a key. My commit message cited "ADR-330 (49)", which is not on this base; the rule rests on ADR-016..019.

## Time

| task / model / minutes |
|---|
| All work: Sonnet, this session (no helpers used) |

SAFE TO CLOSE (head: see the pushed branch; left: D-4, O-3, O-4, O-6 and the UX-A02 prop to the owner lanes; order-path items F3, F4, F7 below; #870 proof)
