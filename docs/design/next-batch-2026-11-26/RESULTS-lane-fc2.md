STATUS 05:30 | item 1: Passed in cloud (paper-alerts.r2-1128.test.js, 4) | item 2: D-6, D-7, D-8, D-11, D-13 Passed in cloud; D-4 Blocked (not my file) | item 3: UX-B04, UX-A09 Passed in cloud; UX-A12 no change in my files | next push: none, queue done | blocker: none

# Lane FC2: pages (Alerts, Positions, strategy lists, chart)

Branch `fix/r2-pages-1128` from `origin/fix/r2-small-screens-1128`. Paper only; no broker call anywhere; no money arithmetic added.

## Status per item

| Item | State | Test (cloud) |
|---|---|---|
| 1 Alerts > History loading line | Passed in cloud | `paper-alerts.r2-1128.test.js` 4 passed, 0 `it.fails` left (the TB `it.fails` is a plain `it`; seen red before the fix) |
| 1 Alerts > Active (UX-A07, UX-A29) | Passed in cloud, no code change needed | same file: the Active cases (8 s pending, empty, failed) were already green on this base; they stay as the proof |
| D-6 OI line printed twice | Passed in cloud | `payoff-oi-r2-fc2.test.js` 4 passed |
| D-7 `NIFTYRunning` | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-7) |
| D-8 empty cells in a closed row | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-8) |
| D-11 paused sentence twice, compact row | Passed in cloud | `paper-pages-r2-fc2.test.js` (D-11) |
| D-13 Real part never re-read | Passed in cloud | `positions-real-reread-r2-fc2.test.js` 5 passed |
| D-4 Add to Paper after the close | Blocked: the dialog is `PaperConfirmDialog.vue` (Lane FA2); `git grep "Add to Paper"` finds no other dialog | exact change below |
| UX-B04 step 4 progress words | Passed in cloud | `create-strategy.test.js` -t UX-B04, 1 passed |
| UX-A09 one notice for the page | Passed in cloud | `paper-pages-r2-fc2.test.js` (UX-A09 x5 + `priceNoticeUp`) 9 passed in the file |
| UX-A12 settled trade | No change: its words ("No draft strategy is open...", Plan watch) are in Lane FB2 and FC3 files; nothing on Positions or the lists | none |
| UX-AF2, UX-B03 | Not retested (time was spent on the items above; both are in the build per the brief) | none |

Whole frontend suite on the final tree: 320 files, 3788 tests passed. ESLint on `src` and my tests: only one warning, in `TrackingPanel.vue` (Lane FC3's file, `LEG_PNL_MISSING` unused), none in mine.

Browser checks (preinstalled Chromium against `vite preview` of a fresh build, `/api` answered by test mocks), shots in `docs/design/next-batch-2026-11-26/screens-fc2/`:
- `alerts-history-loading.png` (24 KB): at 1.5 s with both reads pending the History tab says "Loading..." and not "No stops or expiry settlements yet."
- `positions-paused-one-notice.png` (268 KB): two paused strategies; the paused sentence appears once on the page (counted in the page text: 1; before the fix 2 in the browser, 8 in the unit mount), "NIFTYRunning" absent, the closed row shows "—" in Unbooked and P&L.
- `create-strategy-step4-progress.png` (38 KB): step 4 with the template list pending reads "Loading... Reading the strategy list. This can take up to 20 seconds."

## For the owner lane

**D-4 (Lane FA2, `PaperConfirmDialog.vue`; Lane FB2 for any wiring in `SaveDraftBar.vue`).** The Exit dialog already asks the one market answer (`GET /market/exit-state`) and greys Confirm when it says closed. The Add to Paper dialog (first basket, add rows) never asks it, which is why it opens with an empty Price box and the route then refuses with MARKET_DATA_102.
- `PaperConfirmDialog.vue`, `askMarket()` (about line 147): change
  `if (!props.open || !rows.value.some((r) => r.kind === 'exit')) { ... return }`
  to
  `if (!props.open || !rows.value.length) { ... return }`
  so every dialog with rows (adds and exits) asks once per opening. `canConfirm` (about line 215) already returns false for `closed`, `checking` and `unreadable`, and `marketLine` already prints the server's sentence ("The market is closed. Exits can be placed from 09:15 on <next trading day>." per (60)). For an entry the server sentence may say "Exits"; if the owner wants "Orders can be placed from 09:15 on ...", that is the server's one sentence (Lane FD2), not a second wording in the browser.
- Same file, Price input: while `marketState` is `closed` or `unreadable`, an empty Price box must have the market line beside it (it does once the change above is made, because `marketLine` is printed in the footer); if a draft has no planned entry and the market is open, `PAPER_PRICE_REASON` ("Enter a price in steps of 0.05") stays as is.
- Failing test to add there (Lane FA2): mount the dialog with one `kind: 'open'` row, `GET /market/exit-state` answering `{closed: true, sentence: 'The market is closed. ...'}`; expect `paper-market-closed` shows the sentence and `paper-confirm-button` is disabled; with `{closed: false}` it is enabled once the price is valid.

**`PriceNotice.vue` (shared, not mine):** my new `priceNoticeUp(answer, affected)` in `lib/priceState.js` repeats its show/hide rule so the Positions list can stay quiet exactly when the page notice speaks. When a lane owns `PriceNotice.vue`, it should call that helper instead of keeping its own copy, so the two cannot drift.

**`PositionsTotals.vue` (not in my edit list):** I did not touch it. The list now hands it a Paper total with no paused sentence when two or more strategies are paused (the page notice says it), so the total shows a dash with no reason line under it.

## Decided for the owner

1. **D-4 decided as (60) says for the Exit dialog** (Spec basis: ADR-330 (60), (58) paper equals real): when the market is closed the Add to Paper dialog opens, shows the legs, shows the server's market-closed sentence (the one `GET /market/exit-state` answer, same source as the Exit dialog) and its Confirm is greyed; no empty Price box without a reason line. Not built here (file belongs to Lane FA2); the exact change is above.
2. **D-8:** a closed leg row shows its booked figure, and "—" (the app's one dash) in Unbooked and P&L. It does not repeat the booked figure in P&L, so no figure appears twice. (Spec basis: ADR-330 (62) booked result; "an empty cell is never shown", brief.)
3. **D-6:** the OI line prints the sentence once; if the server's reason already starts with it, the reason is printed as sent.
4. **D-11:** where several lines under one compact row each say the book is paused, the one with the "as of" time is printed (`pausedOnce`, `lib/priceState.js`).
5. **D-13:** the Real part is re-read every 30 s, at once on the browser's `offline` and `online` events, and a figure is hidden after 90 s (the server's `STALE_AFTER_SECONDS`) from the page's own receipt of it, so a hung read cannot keep an old number up. A refused read shows the not-connected message and a dash (the page already did this on first load). Timers and listeners are removed when the page is left; an answer that arrives later is dropped. (Spec basis: ADR-330 (24) real figures from Zerodha, ADR-016 Zerodha is the authority.)
6. **UX-A09:** with two or more open paper strategies paused, the page says the paused sentence once (with its "as of" time, from the strategies' own sentence); tiles are greyed and carry no sentence; figures show a dash with no repeated reason. With exactly one paused strategy, that tile keeps its own line, as ADR-330 (56) says. When the page's own price notice is already showing, the list adds none. A failed refresh (a list held, figures paused) keeps its banner and today's rules; I did not change it.

## New wording for the owner to read

- Create Strategy step 4, under "Loading…" (UX-B04), one line that changes with the stage; the counts are the page's own:
  - "Reading the strategy list. This can take up to 20 seconds."
  - "Reading the planned entry prices of N contracts. This can take up to 20 seconds." (1 contract: "1 contract")
  - "Pricing N strategies: D of N done. This can take up to 20 seconds." (1: "1 strategy")
  The "20 seconds" is the longest wait the PC walk of 28 Nov saw, stated as a limit.
- Positions, hidden Real figure (D-13): "The real P&L figure is more than 90 seconds old and is hidden until the next read." (reworded: Positions code may not name the broker, tests/test_no_broker_name_in_feature_code.py)
- Positions, the page-level paused notice (UX-A09) is the existing sentence, not new: "Paper P&L paused - prices not live, as of <time>".
- D-6, D-7, D-8, D-11, History loading: no new sentence (existing words, once; "Loading..." already existed on Active).

## Not done

- D-4 build (Lane FA2's file; change written above).
- UX-AF2, UX-B03: not retested.
- D-13, "on socket loss": the Positions page opens no feed socket of its own, so I hooked the browser's `offline` and `online` events, not the index socket. If the owner wants the index socket's drop to trigger the re-read too, `PositionsPage.vue` can take `useIndexLive`'s `status` and call `loadReal()` on a change; not built because it opens a second websocket on that page.
- UX-A12: no wording of mine to change.
- Mutation proof: I saw red-then-green for items 1, D-6, D-7, D-8, D-11, D-13, UX-B04 and UX-A09 by running each test before its fix, and for the UX-A09 headline-total case by reverting the fix line; I did not mutate the 90 s boundary or the listener removal by hand.

## To file as deferred issues

- `PriceNotice.vue` should use `priceNoticeUp` (see "For the owner lane").
- `TrackingPanel.vue:100` unused `LEG_PNL_MISSING` (a lint warning that fails `--max-warnings 0` on `src`; Lane FC3's file).

## PC steps

Market closed (after 15:30 IST):
1. Alerts > History: reload; while it reads you see "Loading..." and never "No stops or expiry settlements yet." before the answer.
2. Positions: with the feed down and two or more open paper strategies, "Paper P&L paused - prices not live, as of ..." appears once at the top, not per strategy or per figure; "NIFTY" and "Running" have a gap; open "Show closed positions": a closed row has "—" in Unbooked and P&L.
3. Create Strategy: reach step 4 and click Show strategies; below "Loading…" a line names what is being read and says it can take up to 20 seconds.
4. Positions > Real: open the page with a session; end the session; within about 30 s the Real P&L becomes a dash with "Connect your Zerodha account to continue.", with no reload.
5. Add to Paper after the close: not fixed by this lane (see D-4); expect the old behaviour until Lane FA2 applies the change.

Live (market open):
1. Same as 2 and 4 above with the feed running: the page shows no paused sentence while prices are live; pause the feed and it appears once.
2. Positions > Real: leave the page open for more than 90 s with Zerodha unreachable; the Real figure disappears with the sentence above, and returns after the next good read.
3. Payoff chart on a draft whose expiry has no OI: one line, "OI not available for this expiry: <reason>".
4. Leave Positions for another page and wait 2 minutes: the browser's network log shows no more `GET /api/positions` calls.

## Time

| task / model / minutes |
|---|
| All work: Sonnet, this session (no helpers used) |

SAFE TO CLOSE (head: see the pushed branch; left: D-4 to Lane FA2, socket-loss hook, UX-AF2/UX-B03 retest)
