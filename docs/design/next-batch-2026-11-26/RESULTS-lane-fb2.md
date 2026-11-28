STATUS 05:40 | item 1 double order: Passed in cloud (save-bar-add-lock-r2-fb2.test.js, 11) | item 2 I-49: Passed in cloud (leg-show-at-once-r2-fb2.test.js, 6) | item 3 UX-B25/C3/A12 Passed in cloud (builder-ux-r2-fb2.test.js, 6), UX-A03/AF1 proven already by Lane FB | item 4 D-10 Passed in cloud + browser | next push: this one | blocker: none (merge order: see "For the owner lane" 1)

# Lane FB2: builder page, second batch (branch fix/r2-builder-2-1128, from fix/r2-builder-1128 b741082)

Paper only. No broker order endpoint was called. Money untouched (no arithmetic added; `tests/strategy-table.test.js` ADR-008 scan passes).
Highest status claimed: Passed in cloud (component and page tests with a mocked API, jsdom/happy-dom); NOT tested on the owner's PC, not against a real server.

## Status per item
| item | state | evidence (cloud, this session) |
|---|---|---|
| 1 double order, save-bar path (Opus F2) + F4 | Passed in cloud. Core test RED on the base (5 of 8 failed), green after | `tests/save-bar-add-lock-r2-fb2.test.js`, 11 tests: unknown then Cancel then reopen blocked (no 2nd POST); refused then reopen still needs an edit; refused then legs changed frees it; another strategy not locked; book shows the add stored (lock ends, page told); book read fails (stays locked); book shows no orders inside the window (stays locked); after the window (freed); one `client_request_id` per Confirm, a new Confirm a new key; plus the 3 review cases below |
| 1b the key on the page path | Passed in cloud | `tests/add-to-paper-r2-fb.test.js` (extended): both POSTs carry a `client_request_id`, different keys. Older exact-body tests now expect the key (builder-drafts-mode, exit-all-staged-adr330-59, exit-pending-adr330-49, paper-add) |
| 1c Opus review of item 1 | done, REVISE, all page-side points fixed (below) | Lane FB's own review (page path, unknown-exit 120 s window) was in my base (b741082): second review skipped as the brief allows |
| 2 I-49 leg shown at once | Passed in cloud. RED 5 of 6 on the base | `tests/leg-show-at-once-r2-fb2.test.js`, 6 tests. Browser: `screens-fb2/I-49-leg-shown-at-once.png` (component harness, see "PC steps") |
| 3 UX-A03 | proven already (Lane FB + Lane V); nothing built in `frontend/src` says "If this stop fires"; the sentence is the server's (`backend/ofo/errors/explanations.py` 2105-2127). The fired-stop `paper_monitor.py` line returns none for a fired stop (`tests_app/test_stop_fired_message.py`, not run here: no PostgreSQL) | see "For the owner lane" 4 |
| 3 UX-B25 | Passed in cloud | summary figures hold "Updating the numbers..." while the book is not known to belong to the legs on screen (`tilesHeld`) |
| 3 UX-AF1 | proven already (Lane FB `closedBannerFor`); read-only use of the one as-of rule | no change |
| 3 UX-C3 | Passed in cloud (host flag) / the hiding itself is CSS: browser check not done | Plan watch's own "Loading the rule check..." line is hidden while the page's "Working out the outcome..." is the one line |
| 3 UX-A12/A33 retest | Passed in cloud | settled/completed book: no "No draft strategy is open" (`builder-ux-r2-fb2`, plus the existing `leg-list-empty-states.test.js` item 8) |
| 4 D-10 | Passed in cloud + browser | `screens-fb2/D-10-summary-1366x768.png`, `D-10-summary-1280x800.png`; probe at 480 to 1000 px container width in 2 px steps: no overlapping text, none spilling out of block 1 (it spilled before) |

## Item 1 (what was built)
- `SaveDraftBar.vue`: `addUnknown` store. After an add of unknown outcome (no answer, 5xx, 408/429, cancelled) the strategy's id is locked: `canAddToPaper` (the Add to Paper button and the menu item), `confirmPaper` itself, and the dialog (`:locked`) all refuse. Cancel and reopen do not reset it. It ends only on a read of THAT strategy's Paper book (`readPaperBook`, the one door): orders in the book = stored (the bar records it, tells the page with `paper-added`); a plan with no orders = not stored, believed only for a read SENT more than 120 s + 10 s after the client gave up; a failed read decides nothing. Re-read every 5 s, one read at a time. The lock lives in a store kept for the tab (`sessionStorage`), so leaving the page and coming back, or a reload, keeps it. The plain line shown under the buttons is the existing `ADD_UNKNOWN_TEXT`.
- F4: a 422 refusal is remembered per strategy (`refusedFor`); reopening with the same orders reopens in the refused state, Confirm needs an edit. Legs changed, or lots/price edited before the refusal: a fresh request. A live-price tick alone is not an edit.
- `client_request_id`: `newRequestId()` (`lib/tracking.js`, `crypto.randomUUID`, else `getRandomValues`, else none sent). One new key per Confirm, from the save bar and from the page's "Review and add" (exits and edits included, as the page uses one post function). The page never re-sends on its own, so the same key is never re-sent: a repeat is the server's concern (issues #869, #871). The lock stays: the key makes a resend safe, the lock stops a new press.
- Review (Opus, REVISE) findings and what was done: F1 the dialog's own Confirm came back after its 5 s hold: fixed (`:locked`, guard in `confirmPaper`; test). F3 a read answered after the window but sent inside it freed the add: fixed (window judged by send time + 10 s margin; test). F4 overlapping reads dropped a newer lock: fixed (one read at a time, lock compared by identity). F5 lock lost on remount/reload: fixed (store in `sessionStorage`; test for remount). F7 live-price tick re-armed Confirm: fixed. NOT fixed: F6 only the last refusal is remembered (a second refusal after an edit; no money, REQ-163 nit); F8 after a 511 (index-age) refusal Cancel and reopen resets the "prices not live" tick offer (Confirm stays off until an edit); F9 Save As of a locked strategy gives an unlocked copy of the same legs (a deliberate action). All three are listed in "To file as deferred issues".
- Real twin: the real-order path (Execute page) was not touched; gap listed.

## Item 2 (what was built)
`LegPicker.vue`: `save()` and `addChosen()` emit the leg at once with `capturing: true` and no entry, give the page back (`done`), then `fillCaptures` fills the planned entry in by leg id. A price typed meanwhile stays; a leg removed meanwhile stays removed; a failed capture leaves that leg unpriced with its reason (`needs_reprice` for a Done add) and touches no other leg. `LegList.vue` shows the shared `LEG_WORKING_TEXT` on a `capturing` leg (no capture time, no "not connected"). `buildDraft` sends nothing for a strategy with an unentered leg (unchanged, ADR-075): the outcome request goes out when the entry is in (page test: 0 outcome posts before the reply, 1 after, carrying the entry). Cost: the shape read (`leg-edit`) now goes out twice per add (once when the leg shows, once when its entry is in): two older tests moved from `[2,3,4]` to `[2,2,3,3,4,4]`. `tests/leg-emitters-guard.test.js` got the new emitter `fillCaptures` (allowed: fills an entry on a shown leg, adds/moves/removes nothing), count 6 to 7.

## Decided for the owner
1. After an add of unknown outcome the Add to Paper button is off until the Paper book has been read (spec basis: ADR-017, ADR-016 to ADR-019, REQ-163; ADR-330 (58) paper = real: the same lock exists for exits and for adds on the page path).
2. The key is sent on every post from the builder (adds and exits), not only on adds: one post function, one rule (spec basis: ADR-017).
3. "No order in the book" frees the add only for a read sent 130 s after the client gave up (the server's 90 s worst case + the 30 s margin Lane FB used + 10 s for a slow answer) (spec basis: ADR-017; Lane FB's window).
4. UX-B25: the figures hold "Updating the numbers..." while the trade changed elsewhere, an add or exit was stored but not re-read, or an exit's outcome is unknown (spec basis: REQ-119 AC-4, the one existing updating wording).
5. UX-C3: Plan watch keeps its box and rows but loses its own loading line while the page's line is the one loading line (spec basis: Lane FB's UX-C3 decision).
6. D-10: the four figure boxes (Profit left, Loss left, Max Profit, Max Loss) may wrap onto two lines when the server's text is long, rather than spill (spec basis: none needed; layout only).

## New wording for the owner to read
- None new. Reused as they are: `The last paper order got no answer and may be stored. It is not sent again until the Paper book has been read: open the strategy again to check.` (now also under the save bar), `Working out the outcome...` (now on a leg whose entry is still coming), `Updating the numbers...` (now on four summary figures; exported as `UPDATING_NUMBERS_TEXT`).

## For the owner lane
1. MERGE ORDER, IMPORTANT: `PaperOrdersIn` in `backend/ofo_app/routes/paper.py` (lines about 174-175) is `extra="forbid"` and has no `client_request_id` in this tree (`docs/api/openapi.json` also). Lane FD2 serves it. This branch sends the key on every paper post: until the server accepts it every Add to Paper and Exit from the builder is refused with a 422 (fail closed, no double order, but no order). Merge this after Lane FD2's change, or together. The frontend does not check the key against `openapi.json`.
2. Server: a repeat of the same `client_request_id` must return the first result and place nothing (issues #869, #871).
3. The lock (and Lane FB's exit lock) are per tab (page memory, plus `sessionStorage` for the add lock). A second tab or another device is not covered: only the server key covers it.
4. UX-A03: if the fired-stop toast still shows "If this stop fires...", the text comes from the server's stored row. The fix is in `explanations.py` or the code that writes the `stop_fired` row (Lane FC3): a stop that has fired must not carry the future-tense line. `frontend/src/lib/paperAlerts.js` prints the row as sent.
5. `PlanWatch.vue` (Lane FC3): the cleaner fix of UX-C3 is a prop that says "the page is loading" instead of the page's CSS rule on `[data-testid='plan-watch-loading']`.
6. `usePaperExit.js` / `PaperConfirmDialog.vue` (Lane FA2): the dialog's 5 s unknown hold (`PAPER_UNKNOWN_HOLD_MS`) is a timer, the same kind Lane FB removed for exits; the page and bar now pass `:locked`, so it no longer matters on the builder, but the Positions exit path (`PaperStrategies.vue`) still relies on it.

## Not done
- UX-C3's CSS hiding and UX-B25 were not looked at in a real browser on the whole page (the page needs a live server): item 3 has component and page tests only.
- Real-order twin of the add lock (Execute page): not touched.
- `tests_app/test_stop_fired_message.py` not run (no PostgreSQL in the container).

## To file as deferred issues
- Add lock F6: only the last refusal per strategy is remembered.
- Add lock F8: after a 511 refusal, reopening forgets the "prices not live" tick offer.
- Add lock F9: Save As of a locked strategy gives an unlocked copy.
- The shape read (`/strategies/leg-edit`) is sent twice per added leg (shown, then priced): a bounded extra read; could be skipped for a leg with no entry.

## Tasks / model / minutes
| task | model | minutes |
|---|---|---|
| items 1 to 4, tests, browser checks, this file | Sonnet (this session) | about 40 |
| Opus review of item 1 | Opus | about 6 |

## PC steps
Market closed (any time):
1. `git fetch && git checkout fix/r2-builder-2-1128`, build, start with the Lane FD2 server (see "For the owner lane" 1).
2. `cd frontend && npx vitest run tests/save-bar-add-lock-r2-fb2.test.js tests/leg-show-at-once-r2-fb2.test.js tests/builder-ux-r2-fb2.test.js tests/add-to-paper-r2-fb.test.js`.
3. Builder with two legs of a strategy that has no fixed maximum loss (TC strategy #5) at 1366x768 and 1280x800: "No fixed maximum" stays inside its tile, nothing overlaps "Intrinsic value".
4. Pick a leg and press Done: the leg is in the list at once with `Working out the outcome...`, the price fills in a moment later.
Live (market open):
1. Add to Paper on a saved strategy, cut the network after Confirm (or stop the API) so the post gets no answer, Cancel, press Add to Paper again: it stays off with the plain line; nothing is sent. Restore the network, wait for the Paper book read: the line ends when the book shows the order (or, 130 s after, when it shows none).
2. Time Done to first prices (T2-11: 14 s). The leg now shows at once; the first prices still need the planned-entry reply and the outcome reply.
Browser checks were made on a component harness (the real components, a built bundle served by `vite preview`, Chromium, no server): the harness files were removed before the commit.

SAFE TO CLOSE (head: see the last commit of fix/r2-builder-2-1128; left: merge order with Lane FD2, item 3 browser walk of the whole page, deferred issues above)
