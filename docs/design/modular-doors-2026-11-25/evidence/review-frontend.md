# Modular review: frontend/src (read-only, 2026-11-25)

Paths are relative to `D:\Abhay\Ventures\OptionsForOptions2\frontend\src`. Every file:line below was opened this pass. "unverified" = not proven by reading.
Read first (not redone): `D:\Abhay\scratch\code-map-2026-11-23\frontend.md`, `DUPLICATES.md`. That review found small helper copies (Indian digit grouping, time formatters). This review finds whole user actions and figures built more than once, which it did not cover.

## Summary table (in the order they should be done)

| # | Shared thing | Places now | Shared today? | Defect it explains | Proposed single piece | Size | Risk if left |
|---|---|---|---|---|---|---|---|
| 1 | "Is this screen's price data fresh enough to act on?" (one rule + one wording) | 6 separate checks (see 4) | No | D-05, D-39 | `usePriceFreshness` (composable) | M | Money: exit on stale prices |
| 2 | Exit paper positions | Positions list, builder Net Positions table, builder Exit all, Compare "full exit" | Half: one dialog, two order builders, two POSTs, two gates | D-05 | `usePaperExit` + one `ExitButton` | M | Money |
| 3 | Per-leg LTP and its time | 3 endpoints on the builder alone | No | D-41, D-18 | `usePaperBook` (one read, all consumers) | M | Wrong figure |
| 4 | Not-live / paused wording | 8 strings in 5 files | No | D-39 | one `lib/priceState.js` | S | Wrong figure |
| 5 | Strategy P&L (total, booked, unbooked, after charges, as-of) | 5 readers, 2 pollers of the same endpoint | Partly (`afterFigure`) | D-07 | `PaperPnlBlock` + one reader | M | Wrong figure |
| 6 | Add or move a leg ("one door") | Door in `lib/legDoor.js`; 2 copies of its dialog; several entry points bypass it | Partly | D-60 | `<DuplicateLegDialog>` + `useLegDoor` | S/M | Money (silent double position) |
| 7 | Stops and exits setting | `PaperStops` (Positions only), plan sheet, Preferences plan form | No | none logged | `PaperStops` also in builder | S | Maintenance |
| 8 | Rename / delete / save-name | Rename twice (modal and inline); delete shared | Delete yes, rename no | none | `useRename` | S | Maintenance |

## 1. Exit buttons and dialogs (money; do second, after the freshness rule)

### Places
| Entry | File:line | What it does |
|---|---|---|
| Positions > Paper `Exit (n)` | `components/strategy/PaperStrategies.vue:150` (button), `:312-319` `ask()`, `:322-348` `doExit()` | Ticks open contracts, builds rows with `exitRowsFor` (`lib/paperList.js:200`), opens `PaperConfirmDialog` (`:160`), POSTs `/paper/strategies/{id}/orders` itself (`:329`). |
| Builder Net Positions per-leg `Exit` + lots box | `components/strategy/PaperBookPanel.vue:78-84` (box + button), `:138-139` `exitOne` emits `exit` | Page handler `exitPaper` `pages/StrategyBuilderPage.vue:443-449` turns it into edited legs (`legsAfterExit`, `lib/paperDrafts.js:295`), then `reviewPending` (`:429`). |
| Builder `Exit all` | `PaperBookPanel.vue:16`; page `exitAllPaper` `StrategyBuilderPage.vue:438-442` | Sets legs to `[]`, then `reviewPending`. |
| Compare (adjustment) "full exit" | `components/strategy/AdjustCompare.vue:388-396` emits `prepare` with `exit`; page `prepareApproach` `StrategyBuilderPage.vue:132-153`, calls `exitAllPaper()` at `:151` | Third entry; rides the builder path. |
| Live Strategies card | `components/live/LiveStrategyCard.vue` | No exit at all (grep: no match). Read-only. |
| Real-order exit | `pages/ExecuteStrategyPage.vue:149` `prepare('EXIT')` | A different thing (Kite basket form, real broker). Not in scope of the paper exit, but it is the only place that is "exit a real strategy". |

### Shared or separate
- Shared: the dialog `PaperConfirmDialog.vue` (both screens, `StrategyBuilderPage.vue:1066`, `PaperStrategies.vue:160`), the outcome classifier `paperPostOutcome` (`lib/tracking.js:58`), and the rule that the server prices the exit (`PaperConfirmDialog.vue:21-24`).
- Separate:
  1. Order builders: Positions uses `exitRowsFor` (`paperList.js:200`); builder uses `paperOrdersFor` + `confirmRowsFor` (`paperDrafts.js:103`, `:148`). Both end in the same shape, written twice.
  2. The POST: Positions calls `api.post` inline (`PaperStrategies.vue:329`); builder calls `addToPaper` (`lib/tracking.js:75`, used at `StrategyBuilderPage.vue:470`). The builder one also sends suggestion ids and the held block.
  3. Success handling: Positions closes the dialog and refreshes (`:343-347`); builder keeps the dialog open in a "placed" state and re-reads with retries (`:479-495`, `PAPER_REREAD_DELAYS_MS`, `paperDrafts.js:199`).
  4. "Can I exit now?": see difference below.
  5. Lots: Positions exits whole open lots only (`canExit`, `:257`); builder allows a partial lots box (`PaperBookPanel.vue:139`, `exitLotsOk`).

### Real behaviour difference (this is D-05)
- Positions gates on `stale` = a failed or unreadable read with a list on screen (`PaperStrategies.vue:240`, `listIsStale` `paperList.js:186`). It disables the button (`:150`), shows `NOT_LIVE_EXIT` (`:151`), refuses in `ask()` (`:314`) and again in `doExit()` (`:325`), and closes an open dialog on a failed read (`:269`, `:276`).
- The builder gate is `paperStale` only (`StrategyBuilderPage.vue:410`, `:439`, `:444`). That flag means "orders were just stored and the re-read has not landed". It does NOT include `paperReadFailed` (set by the book read, `lib/usePaperBookRead.js:23`). So when the server is down:
  - `exitAllPaper` / `exitPaper` only test `!paper.value || paperStale.value` (`:439`, `:444`): both stay open.
  - `PaperBookPanel` gets `readFailed` (`:1064`), but the template only uses it for the "paused" sentence (`PaperBookPanel.vue:105-106`). The `Exit all` button (`:16`) has no `disabled` at all; the per-leg `Exit` is disabled only by the lots box (`:83`).
  - The confirm dialog prices from the LAST good book: `confirmRowsFor` reads `p.price_state === 'live'` of the stale book (`paperDrafts.js:151-153`), so a stale "live" price is shown as "about X, as of T".
  - Proven by reading; the screen behaviour in D-05 matches. The server-down click test itself was not run (read-only).
- Smaller difference: the Positions dialog closes itself when a later read changes the group's open contracts (`settle`, `PaperStrategies.vue:298-306`); the builder does not (it shows `contractsChanged` text instead, `PaperBookPanel.vue:24`).
- The owner's "exit at limit if asked" does not exist anywhere in the paper path: the dialog says "the server sets the exit price when you confirm" (`tracking.js:48`, used `PaperConfirmDialog.vue:24`) and `orderOf` sends price `'0'` for exits (`PaperConfirmDialog.vue:~110`, `orderOf`). A limit exit is a new feature, not a refactor. unverified: whether the server accepts a limit exit price (the client throws the typed value away for exits).

### Proposed single piece
- `composables/usePaperExit.js` (name `usePaperExit({ strategyId, book, readOk, onDone })`).
  - Inputs: the book reply (positions, lots, ltp, price_state), a `readOk` flag from the freshness rule (item 2 below), optional contract ids and lots (default: all open), later an optional `limitPrice` per leg.
  - Outputs: `canExit` (boolean) and `reason` (the one sentence, from the shared wording file), `ask(selection)` (opens the dialog), `dialogProps` (rows, busy, error, state), `confirm()`, `cancel()`. Internally: ONE row builder, ONE `addToPaper` POST, ONE state machine (ready / refused / unknown / placed), ONE "cancel when the open contracts changed" rule.
  - Used by: Positions list, builder Net Positions per-leg, builder Exit all, Compare full exit, and any rule or stop that later needs "exit this strategy now".
- A tiny `ExitButton.vue` that takes `canExit` + `reason` and renders disabled-with-reason the same everywhere (replaces the three hand-written buttons: `PaperStrategies.vue:150`, `PaperBookPanel.vue:16`, `:83`).
- Server side note (outside this review): an exit that is accepted while prices are stale should also be refused by the server; the browser guard alone is not a control. unverified: whether the server does.

### Risk if left
Money. The two paths already differ in the one place that matters (D-05). A fix applied to Positions will not reach the builder, which is exactly what happened.
### Size and order
M. Do after item 2 (shared freshness rule) because the gate is its input. Quick safe first step (S): make `exitAllPaper` / `exitPaper` / the two buttons honour `paperReadFailed` today, then replace by the composable.

## 2. Price freshness: "may I act on these prices?" (do first)

Six places each decide this on their own:
| Place | Condition | File:line |
|---|---|---|
| Positions Paper list | `stale = failed read && list on screen` | `PaperStrategies.vue:240`, `paperList.js:186` |
| Builder paper book | `paperReadFailed` (display only) + `paperStale` (a different thing) | `usePaperBookRead.js:23`, `StrategyBuilderPage.vue:410` |
| Builder outcome / legs | `state` 'stale' / 'not-connected', `live.reconnecting`, `socketDropped` | `StrategyBuilderPage.vue:313`, `:976-987` |
| Tracking panel | `view.kind` paused / not_connected from the tracking reply | `lib/tracking.js:249-259` |
| Live Strategies card | `down`, `notConnected`, `fromEntries`, `paused` | `LiveStrategyCard.vue:166-170` |
| Home / My Strategies / Live P&L line | `stale = failed && list` again, in `usePaperPnl` | `lib/paperPnl.js:46` |

Proposed: `composables/usePriceFreshness.js` taking the read result (ok / failed / error, reply state, answered_at, per-leg price_state) and returning `{ live, paused, reason, asOf, canAct }`. One rule, one sentence, one time. Every screen above asks it. Size M. Risk: money (item 1) and wrong figures (item 4).

## 3. Live price / LTP per leg

### Sources (builder screen alone has three)
| Display | Data source | File:line |
|---|---|---|
| Builder leg rows + outcome table | outcome reply `legs[].ltp` / `ltp_display` / `leg_quotes[].quote_at`, pushed by the strategies socket | `StrategyBuilderPage.vue:956-962`, `LegList.vue:93-98`, `:234` |
| Builder Net Positions table (paper-legs) | paper book `positions[].ltp_text`, `price_at` from GET `/paper/strategies/{id}` | `PaperBookPanel.vue:67`, read by `lib/usePaperBookRead.js:21` |
| Builder "Paper P&L (not real)" panel | tracking reply `legs[].current_price_display` from GET `/strategies/{id}/tracking`, only when `price_state==='live'` | `TrackingPanel.vue:32`, `lib/tracking.js:225`, read `TrackingPanel.vue:218-222` |
| Positions paper rows | list reply `positions[].ltp_text` from GET `/paper/strategies` | `PaperStrategies.vue:128`, `paperList.js:58-59` |
| Live Strategies card | the strategies socket answer (own follow) | `LiveStrategyCard.vue` (via `useStrategyLive`) |
| Option chain | chain socket `/market/chain/live` | `OptionChainPage.vue:48` |
| Leg picker | GET strikes (`prices_at`) | `LegPicker.vue:203` |
| Depth popup | GET `/leg-picker/depth` | `DepthPopup.vue:30` |
| Exit/entry dialog rows | book `ltp_text` for exits; outcome `ltp_display` for entries | `paperDrafts.js:148-170`, `tracking.js:66` |

### D-41 root cause (found in code, not run)
`TrackingPanel` is mounted with `:shared="paper?.book"` (`StrategyBuilderPage.vue:1255`) but uses `shared` ONLY for the headline total (`TrackingPanel.vue:~102-108`). Its per-leg LTP column comes from its own `/tracking` read on its own 5 s timer (`TrackingPanel.vue:241-257`, `TRACKING_REFRESH_MS` 5000 at `tracking.js:103`). The Net Positions table uses the page's book read, a separate 5 s timer (`usePaperBookRead.js:20`). Two endpoints, two timers, two quote moments: 150.00 vs 150.95 at the same second is expected from this design. The earlier "F4" fix (`tracking.js:174-177` comment: "the paper panel, the tracking box and the P&L table TOTAL row all show this") shared the headline total only, not the legs.
Also: nothing on the Positions rows or the Tracking panel shows a per-leg quote time, while the Net Positions table does (`PaperBookPanel.vue:67`, `net-ltp-at`).

### Proposed single piece
- `composables/usePaperBook.js` (a Pinia store or provide/inject, keyed by strategy id): the one read of GET `/paper/strategies/{id}`, with `book`, `readFailed`, `answeredAt`, `ltpFor(contractId) -> { text, at, live }`. Net Positions, Tracking panel legs, confirm dialog rows, and Positions rows (via the list reply, same field names) all call `ltpFor`.
- `<LegPrice :text :at :live>` component: one look (price plus HH:MM:SS, or "time n/a", or a dash with the reason).
- Ask the server (not a browser job): whether `/tracking` legs can carry the same quote as the book. If `/tracking` is only needed for detections and rule checks, drop its leg-price columns. unverified: what else the tracking reply feeds.
Size M. Risk: wrong figure shown to a user deciding to exit. Depends on item 2 for the "not live" half.

## 4. "Prices not live / paused / stale" wording

Strings that say the same thing, in different words or constants:
- `NOT_CONNECTED_TEXT` `tracking.js:108` and `PAPER_NOT_CONNECTED` `paperList.js:16`: identical text, two constants.
- `pausedText(asOf)` `tracking.js:116-118` and `withAsOf(PAPER_PAUSED, as_of)` `paperList.js:30`, `:15`, `:123`: same words, two builders.
- `PAPER_PAUSED` used again as the note in `paperPnl.js:24`.
- `NO_TOTAL`, `NOT_LIVE_EXIT` `PaperStrategies.vue:188`, `:190` (local).
- `PAPER_BOOK_UNREADABLE` `paperDrafts.js:18`, `UNREADABLE_TEXT` `tracking.js:109` (different wording for "could not read").
- `RECONNECTING_PREFIX` `sharedStateText.js:14`, builder `pricesStamp` `StrategyBuilderPage.vue:976-987`, the market-closed banner (`MarketClosedBanner`), `Index values are not live` `IndexStrip.vue:15`.
- D-39: `SummaryCards.vue:160` prop `timeValueBasis` is the server's text "at live prices, as of HH:MM:SS" shown unconditionally; nothing there ties it to the page's not-live state. unverified: where it is rendered (not read past line 160); cause is probably that the text comes from the server and the page does not blank it when `state` is stale / `socketDropped`.

Proposed: one `lib/priceState.js` holding the constants and `priceStateText(state, asOf)`; every file imports it. Size S. Risk: wrong message; also the reason D-39 can happen without any test failing.

## 5. Strategy P&L figures (total, unbooked, booked, after charges, as of)

### Places and readers
| Screen | Reader | File:line |
|---|---|---|
| Positions Paper list (strip + cards) | `readPaperList` | `paperList.js:113-184`, rendered `PaperStrategies.vue:14-26`, `:78-87` |
| Builder Net Positions strip | `sharedTotal(book)` + `afterFigure` | `PaperBookPanel.vue:~100-116`, `tracking.js:161-190` |
| Builder tracking headline | `sharedTotal` (when `shared`) else `readTracking` | `TrackingPanel.vue:~100-108`, `tracking.js:210-263` |
| Builder summary tiles ("Profit left / Loss left") | `paperLeftOf(book)` | `paperDrafts.js:219`, `StrategyBuilderPage.vue:~455` |
| Builder chart table TOTAL row | page's `paperTotal` = `sharedTotal` | `StrategyBuilderPage.vue:427`, `ChartCard.vue:67` |
| Live card, My Strategies row, Home | `usePaperPnl` -> `readPaperList` | `lib/paperPnl.js:42-65`, `components/live/PnlLine.vue` |
| Live card max profit / loss | paper book texts | `LiveStrategyCard.vue:~176-182` |
| Tracking list item | `readTrackingItem` | `tracking.js:272-315` |

Same engine texts, but the reading is in `tracking.js` (`readTracking`, `readTrackingItem`, `sharedTotal`), `paperList.js` (`readPaperStrategy`, `readTotals`) and `paperDrafts.js` (`paperLeftOf`): three parsers of overlapping fields from three endpoints. `afterFigure` is the one shared bit (`tracking.js:161`).
Also: the same endpoint `/paper/strategies` is read by two pollers on different pages: `PaperStrategies.vue:243-248` and `lib/paperPnl.js:42-52` (Home, Live, My Strategies). On the same page they would not be in sync. unverified whether any page mounts both at once (Positions mounts `PaperStrategies`; `usePaperPnl` is used by Home, Live, My Strategies, `paperPnl.js` consumers list above).

### D-07 and D-18, found in code
- D-07: `sharedTotal` produces a line "As of HH:MM:SS IST" from `answered_at` when live (`tracking.js:182-185`). `PaperStrategies.vue` and `paperList.js` never read `answered_at` (the only `as_of` use is inside paused sentences, `paperList.js:123`, `:126`, `:158`, `:174`). So the builder total has a time and the Positions total does not, by construction.
- D-18: the quote time is shown per leg only in the builder Net Positions table (`PaperBookPanel.vue:67`), `LegList.vue:93-98` ("Oldest leg price as of"), `PaperConfirmDialog.vue:22`, `LegPicker.vue:203`, `OptionChainPage.vue:162`. Positions rows and the tracking panel show none. Different panels print different stamps for one moment because they read different replies.

### Proposed single piece
- `components/strategy/PaperPnlBlock.vue`: input is ONE normalised object `{ total, booked, unbooked, charges, decay, asOf, state, reason }` from ONE reader `lib/paperFigures.js` (merge the three parsers behind `readPaperStrategy`, which already carries `totalAfter / bookedAfter / unbookedAfter`). It renders the label ("after charges" or "before charges"), the breakdown tap (`AfterChargesTap`), the paused sentence from item 4 and the `As of` line, always.
- Used by: Positions strip and cards, Net Positions strip, TrackingPanel headline, Live card line, My Strategies row, Home.
Size M (rendering is easy; moving the three parsers under tests is the work). Risk: wrong or untimed figure; D-07 and D-18 are symptoms.

## 6. Add or move a leg: "one door"

### What exists
`lib/legDoor.js:1-40` is the door (`admitLegs`, `sameContract`: same instrument id and same action; Increase / Keep separate / Cancel). Used at:
| Entry point | Goes through door? | File:line |
|---|---|---|
| Picker form Save (add or edit a leg) | Yes | `LegPicker.vue:531` |
| Picker Done (ticked strikes) | Yes | `LegPicker.vue:588`, `:599-605` |
| Picker future Buy / Sell | Yes | `LegPicker.vue:654` |
| Strike step +/- | Yes, after the server move | `StrategyBuilderPage.vue:759-777` `askMovedDuplicates`, called `:808` |
| Shift / Width / Hedge | Same code (`RELATIVE_CONTROLS`, `legEdit.js:54`) | same |
| Ready-made shapes | No door; replaces the whole list via `update:legs` | `ReadyMadePanel.vue:94`, `StrategyBuilderPage.vue:1075` -> `setLegs` |
| Open from a link / Option Chain page -> builder | No door; the whole list is seeded from the query | `StrategyBuilderPage.vue:105-120` `legsFromQuery`; chain page `OptionChainPage.vue:3`, `stores/chainSelection.js` |
| Compare approach "Open in builder" | No door; `setLegs(next)` / `keepHeldFills` | `prepareApproach` `StrategyBuilderPage.vue:132-170` |
| Lots / Multiplier / Include / Price edits | Not a contract change; not applicable | `legEdit.js:40-50` |
| Same-contract warning in the leg list | A passive note, not the door | `LegList.vue:84-90`, `:267` |

So the rule lives in one library function (good), but the dialog that asks it is written twice and the two callers are wired separately:
- Dialog copy 1: `LegPicker.vue:676-684`. Dialog copy 2: `StrategyBuilderPage.vue:996-1004`. Same test ids, same buttons.
- Ask state machine twice: `LegPicker.vue:511-515` (`dup`, `answerDuplicate`) and `StrategyBuilderPage.vue:739-756` (`dupAsk`, `cancelDuplicate`, `answerDuplicate`).

### D-60 (strike step onto a held contract asked nothing)
Code path is present (`StrategyBuilderPage.vue:803-815`), so the cause is not "the door was never wired". Candidates, none proven: (a) `askMovedDuplicates` only asks for legs whose `instrument_id` changed against `baseLegs[i]` by INDEX (`:760`) and tests against legs that did not move (`:762-763`); (b) `sameLegs(legs.value, shown)` returns silently when the legs changed during the wait (`:809`); (c) `sameContract` needs equal `action` (`legDoor.js:15`), so Buy onto a held Sell is by design a second leg; (d) a leg with `included:false` is still matched. Cannot decide without running; unverified. The single-source fix below removes the second wiring, which is the likeliest place the gap hides.

### Proposed single piece
- `components/strategy/DuplicateLegDialog.vue` (props `open`, `name`; emits `answer`) and `composables/useLegDoor.js` returning `{ ask, dialogProps, admit(held, incoming, opts) }` that owns the pending promise and the cancel-on-newer-edit rule. LegPicker and the builder both call `admit`; every other way to change legs (ready-made, link, approach) calls the same `admit` with `ask` returning 'separate' by default, or the dialog, so no entry can bypass it.
- A contract test: "every `update:legs` emitter calls `admit`" so the next entry point cannot forget.
Size S for the dialog + composable, M if the three bypass entries are brought through the door (they replace, not add, so the real rule there is open: owner decision whether a ready-made shape on a non-empty strategy should ask; the spec line is not in the code).

## 7. Stops and exits

- `PaperStops.vue` (arm Conditional exit, per-leg Stop, list, cancel, keep): used only by `PaperStrategies.vue:169`, `:153` (Positions full cards). The builder shows armed exits read-only through `PlanEntry.vue:42` fed by `TrackingPanel.vue:172-179` (`/paper/strategies/{id}/triggers`). So a stop can be set only on Positions, listed in the builder, and each uses its own read of `/triggers` (PaperStops `:80` `api.get(path)`; TrackingPanel `:175`).
- Plan stop (percentage): `AdjustPlanSheet.vue:29-31` and the Preferences per-strategy plan form `PreferencesTab.vue:403`, both on `lib/adjustPlan.js`.
- Date/target (not a stop): `TargetBlock.vue`.
- "Not saved:" lines: `PaperStops.vue:51-53` only; the Save Draft bar and rename use `errorParts` / `ErrorMessage` instead.
Proposed: expose `PaperStops` in the builder next to the book (it already takes `strategyId`, `legs`), and have `TrackingPanel` read the triggers from the same composable. Size S. Risk: maintenance only; no figure or order differs.

## 8. Rename, delete, save-name

- Delete: shared. `useDeleteFlow` (`lib/strategyActivity.js:106`) + `DraftDelete.vue` + `DraftDeleteStatus.vue`, used by `MyStrategiesPage.vue:162` and `SaveDraftBar.vue:518`. Good example of the pattern wanted.
- Rename: two UIs, one call. Builder modal `SaveDraftBar.vue:262-282` (revision from `props.current`); list inline `MyStrategiesPage.vue:114-129` (first reads GET `/strategies/{id}` for the revision, fails closed). Both end in `renameStrategy` (`lib/saveDraft.js:67`). Different revision source; same server write. Error display differs (`errorParts` vs `renameError`).
- Save-name box: only in `SaveDraftBar.vue:462`.
- Other confirm dialogs, one-off by design: `BrokerSettingsPage.vue:160`, `AdjustmentsPage.vue:303`, `ReadyMadePanel.vue:154`, `LegPicker.vue:726`.
Proposed: `composables/useRename.js` taking `{ id, getRevision }` and returning `{ text, busy, error, confirm }`. Size S. Risk: maintenance (two revision rules).

## Do-first order and why
1. Item 2 (freshness rule + wording, item 4) — it is the input to every exit and figure.
2. Item 1 (one exit capability) — the owner's example; money at stake; needs 2.
3. Item 3 (one paper-book read) then item 5 (one P&L block) — fixes D-41, D-07, D-18 together; needs the shared read.
4. Item 6 (door dialog + guard test), then 7, 8 (small).

## What I did not check
- No code was run; no test was opened; behaviour above is from reading.
- Not read in full: `StrategyBuilderPage.vue` (1260 lines; read the exit, paper book, leg-edit, tracking and price-stamp parts), `SummaryCards.vue`, `LegPicker.vue` (read the add, save and door parts), `AdjustCompare.vue` beyond the exit lines, `ChartCard.vue`, `lib/legPicker.js`.
- Whether the server refuses an exit on stale prices, and whether it accepts a limit price on an exit: not checked (backend out of scope).
- Spec and decision rows (D-05, D-07, D-18, D-39, D-41, D-60, ADR-319, REQ-109) were not re-read; defect numbers are as given in the brief.
