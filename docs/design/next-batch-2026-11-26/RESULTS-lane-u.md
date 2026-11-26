# Lane U results: fixes for Lane T's screen-suite findings (26 Nov 2026)

Branch `fix/suite-findings-1126`, cut from `origin/fix/screen-findings-1126` 7bf64eb, with `origin/test/screen-suite-1126`
(Lane T's tests, inventory, docs) and `origin/fix/ic-live-test-1123` (ADR-330 answers, coverage rows) merged (a9ab6d2d).
No PR. Paper only. Standing-direction step 4 item 10 (defects in what is built). Highest status claimed: **Fixed, not
tested** (the owner tests on his PC).

Spec basis: ADR-002, ADR-003, ADR-008, ADR-193 (4), ADR-328 (1) and (4), ADR-329 (1) and (3), ADR-330 (10), (17), (19),
(20), (22); REQ-009 AC-5, REQ-015 AC-10, REQ-029 AC-5 and AC-10, REQ-030 AC-12 and AC-15, REQ-044 AC-3, REQ-065,
REQ-109 AC-5, REQ-134 AC-1, AC-3, AC-4, REQ-138, REQ-148 AC-2, REQ-154, REQ-162.

How it was checked: each finding's Lane T browser test (stubbed API, built app on `vite preview`, mobile-390 and
desktop-1280) was red under its `test.fail()` mark; the mark is removed and the test passes. Owner questions:
`owner-questions-lane-u.md` (U-Q1 to U-Q8); reversible recommendations are built.

## Base run (merged base a9ab6d2d, before any Lane U fix)

12 expected-fail tests already passed (Lane R's fixes): N-18 x2 (`R-06`, `FIG-2`), NEW-T03 (`STALE-3`), N-01 (`STOP-11`),
N-14 cards (`LINK-11`), N-05 (`PP-20`), N-04 (`PP-22`), N-07 (`PP-24`), row 12 (`PP-27`, `A12`, `A12b`), NEW-T65 / N-13
(`ST-1`). Marks removed in 1bf1a4d2. The same run found stale Lane T expectations against decisions made after Lane T's
base (corrected to the spec text, never loosened): list labels with the trade number (ADR-330 (19), 39 tests), "1 of
them is running." (REQ-070 AC-7), LV-10 "pending change" (ADR-330 (22)), CHAIN-23 ticks cleared after Add Selected
(ADR-330 (20)); two test races fixed (EXIT-17c clock before the hold timer existed; STOP-9 stub list contradicting its
own POST); inventory guard rows SHARED-41, BUILD-09 updated, MYSTR-15..18 added.

## Triage and final state per id

| Id | Screen | Class | Final state | Root cause (one sentence) | Class size before -> after | Commit |
|---|---|---|---|---|---|---|
| N-18 (x2) | Home | already fixed on base | PASS, mark removed | Lane R (doubled suffix) | - | 1bf1a4d2 |
| NEW-T01 | Home | defect, deferred | expected-fail kept; issue #433 (sign-in, stage 4c) | Welcome name and trial need a signed-in user | - | - |
| NEW-T02 | Home | defect, fix now | Fixed, not tested | `readTotals` built the paused sentence without the reply's `totals_as_of` | paused sentences without as-of: 2 screens -> 0 (one maker in `paperList.js`) | f0069c41 |
| NEW-T03 | Home | already fixed on base | PASS, mark removed | Lane R (same path as N-18) | - | 1bf1a4d2 |
| NEW-T10 | My Strategies | product question U-Q1, recommended built | Fixed, not tested | The rename box had no Escape handler | forms ignoring Escape on the page: 1 -> 0 | 3dded597 |
| NEW-T11 | My Strategies | defect, fix now | Fixed, not tested | The shared API client handed a non-JSON 200 body (proxy HTML) to callers as data, read as an empty list | callers able to take a non-JSON 2xx as data: ~86 -> 0 (one rule in `services/api.js`) | f0069c41 |
| NEW-T20 | Current positions | defect, fix now | Fixed, not tested | A 200 without the `strategies` list was read as no positions | 1 -> 0 (`hasShape` in the shared client) | f0069c41 |
| NEW-T21 (N-05) | Current positions | defect, fix now | Fixed, not tested | The shared `ExitButton` set `disabled` with no disabled style | Exit/commit buttons that look enabled while blocked: 4 -> 0 (one component) | 88d8d45d |
| NEW-T22 (N-04) | Current positions | defect, fix now | Fixed, not tested | Four page-side closes of the Exit dialog left the ticks | page-side closes leaving ticks: 4 -> 0 (one `closeByPage`); the user's own Cancel keeps them (new test EXIT-6b) | 88d8d45d |
| NEW-T23 | Current positions | defect, fix now | Fixed, not tested | A failed first paper read held no list, so the total was not marked paused | 1 -> 0 | f0069c41 |
| NEW-T24 | Current positions | product question U-Q2, recommended built | Fixed, not tested | Same shared-client hole: a non-JSON broker status read as "not connected" | (in the NEW-T11 class) | f0069c41 |
| N-01 | Current positions | already fixed on base | PASS, mark removed | Lane R | - | 1bf1a4d2 |
| N-14 | Live Strategies | already fixed on base | PASS, mark removed | Lane R | - | 1bf1a4d2 |
| N-14 (alerts) | Alerts | Lane P's area | expected-fail kept (`ACT-17`); note for the join | alert titles are the alert module's | - | - |
| NEW-T31 | Adjustment opportunities | defect, fix now | Fixed, not tested | (in the NEW-T11 class: an HTML 200 inbox read as empty) | (in the NEW-T11 class) | f0069c41 |
| NEW-T32 | Adjustment opportunities | defect (observation), fix now | Fixed, not tested | Outcome and detail were adjacent spans with no text between | joined spans: 2 -> 0 | 3dded597 |
| row 12 (x4) | Builder / Option Chain | already fixed on base (3); stale test (chain ROW-12) | PASS, marks removed | Lane R; ROW-12 asserted the pre-fix 4 legs after Back, against ADR-329 (1) and its own later lines | - | 1bf1a4d2, e4edea02 |
| NEW-T40 | Option Chain | product question U-Q3, recommended built | Fixed, not tested | The chain printed the raw ISO expiry | raw ISO on chain surfaces: 3 -> 0 | ea58705d, fa5d4b8e |
| NEW-T41 | Option Chain | product question U-Q3, recommended built | Fixed, not tested | The chain had its own contract-name template | second name formatters: 1 -> 0 (builder's `contractName`) | ea58705d, fa5d4b8e |
| N-04, N-05, N-07 | Builder | already fixed on base | PASS, marks removed | Lane R | - | 1bf1a4d2 |
| NEW-T50 | Builder | defect, fix now | Fixed, not tested | `removeLeg` only filtered the list; the Undo could start only from Clear all | removal paths with Undo: 1 of 2 -> 2 of 2 (same Undo, same served window) | 80049722 |
| NEW-T51 | Builder | not a defect (U-Q4 answered (a), coordinator 26 Nov) | test corrected to the spec, PASS | "Pick from Option Chain" opens the picker's strike view inside the builder by design (W-195 review 7); the full chain is Market > Option Chain; REQ-029 AC-5 now says so | - | 7f887a37 |
| NEW-T52 | Builder | defect, fix now | Fixed, not tested | Modal and Drawer were both `z-50`; the later-mounted drawer covered the dialog | dialogs that open under a drawer: 7 -> 0 (Modal primitive) | 80049722 |
| NEW-T53 / NEW-T68 | Builder (phone) | U-Q5 answered (a) (coordinator 26 Nov) | Fixed, not tested | The 520 px drawer pushed its edge tab past a 390 px screen | drawers whose way back leaves a phone screen: 1 -> 0 (Drawer primitive: below 640 px full width, the control in the drawer's own header; REQ-080 AC-10) | 572c568f, 2211842b |
| NEW-T60 | Builder | defect, deferred + question U-Q6 | expected-fail kept; issue #751 | REQ-154 not built (it stands, ADR-330 (34); built with sign-in); ADR-329 (3) is what ships until then | - | - |
| NEW-T61 | Builder | defect, fix now | Fixed, not tested | The catalogue text was "The strategy has no name." | empty-name texts differing from REQ-134 AC-1: 1 -> 0 | 359af7db |
| NEW-T62, NEW-T63 | Builder | defect, deferred | expected-fail kept; issue #750 | REQ-138 not built (needs server storage: a migration) | - | - |
| NEW-T64 | Builder | defect, fix now | Fixed, not tested | The saved list printed its own literal instead of the shared `noMatchText` | 1 -> 0 | 359af7db |
| NEW-T65 (N-13) | Builder | already fixed on base | PASS, mark removed | Lane R | - | 1bf1a4d2 |
| NEW-T66 | Builder | U-Q7 answered (owner, ADR-330 (37)) | Fixed, not tested | The open-by-id route answered the generic not-available reply, and the page showed the connection line for it | missing-strategy opens without the specific sentence: 1 -> 0 (catalogue `strategy_not_found`, pin pending owner read; "Open My Strategies" link; REQ-134 AC-5). A bare 404 elsewhere stays the neutral message (af807755's blanket mapping reverted in e2f74915: it broke Home FAIL-3 and Live FAIL-4) | 9972cae7, e2f74915 |
| NEW-T67 | Builder | defect, fix now | Fixed, not tested | `renameRow` cleared its pending id before the async open finished | 1 -> 0 | 359af7db |
| NEW-T70 | Orders placeholder | defect (observation), fix now | Fixed, not tested | The note described the old strategy-linked scope | 1 -> 0 | 5d3a1f91, 9d485211 |
| NEW-T71 | Placeholders | defect (observation), fix now | Fixed, not tested | One developer sentence on every placeholder | 15 -> 0 (`COMING_LINES` in nav.js, REQ-009 text; "your broker" wording per the broker-name guard; one page on the fallback line pending an allow-list line) | 5d3a1f91, 9d485211, 23ec7b9a |
| U-Q8 (label year) | My Strategies, Live, Home, Positions | coordinator 26 Nov (a) | Fixed, not tested | List pages never learnt the server's shown date, so every label kept the year | list pages printing the year inside the shown year: 4 -> 0 (`shown_date` on GET /strategies and GET /paper/strategies; one reactive shown date in displayFormat.js) | 7397330f, 44afc32d |

Detection: the un-marked Lane T tests are the detection for each class, plus `frontend/tests/api-unreadable-body.test.js`
(the shared client's rule) and EXIT-6b (Cancel keeps the ticks). Spec text changed: REQ-009 (wording of unbuilt pages),
REQ-030 AC-15 (the leg Undo), catalogue `strategy_name_empty`.

## Re-test: U-Q8 (dates in lists)

1. My Strategies, Live Strategies, Positions > Paper. Expected: labels read "IC wk1 (#172, 1 Dec)" and legs "NIFTY 1 Dec
   25650 PE": no year for an expiry in this year; a next-year expiry keeps its year.

## Re-test: NEW-T11, NEW-T20, NEW-T24, NEW-T31 (unreadable answers)

1. Not clickable on a healthy PC: the case is a proxy or gateway answering an HTML page instead of the app's JSON.
2. To see it: stop the API while the frontend still serves (as in row 4 of the 23 Nov test), then open My Strategies,
   Current positions and Positions > Adjustment opportunities.
3. Expected: each shows its failure message with Retry, never "You have no saved strategies yet", an empty inbox
   "Showing 0-0 of 0 rows", a blank Real section, or "not connected".
4. Start the API again and press Retry: the lists come back.

## Re-test: NEW-T02, NEW-T23 (paused totals)

1. During market hours stop the price feed (as in Part C). Open Home.
2. Expected: "Paper P&L paused - prices not live, as of <date>, <time> IST" with the time of the last price.
3. Reload Positions while the API answers an error for the paper list: the Paper total shows the same paused reason line,
   not a bare dash.

## Re-test: NEW-T21, NEW-T22 (Positions > Paper > Exit)

1. Positions > Paper: tick one leg of a running trade; "Exit (1)" is blue.
2. Stop the API for a few seconds. Expected: "Exit (1)" turns grey (dimmed, no-entry cursor) with the reason line.
3. Start the API, tick a leg, click Exit; while the dialog checks, stop the API. Expected: the dialog closes by itself
   and the tick is cleared ("Exit (0)") once prices are back.
4. Tick a leg, click Exit, press Cancel yourself. Expected: the tick stays ("Exit (1)").

## Re-test: NEW-T10, NEW-T32

1. My Strategies > Rename on any row; type a few letters; press Esc. Expected: the box closes, the old name is shown,
   nothing is saved.
2. Positions > Adjustment opportunities: a dismissed opportunity reads "You dismissed this" and its reason as separate
   words (a screen reader pauses between them).

## Re-test: NEW-T40, NEW-T41 (Option Chain dates)

1. Market > Option Chain. Expected: the Expiry selector reads "1 Dec (5 days)", never "2026-12-01".
2. Tick a contract and press Buy. Expected: Selected Legs reads "NIFTY 1 Dec 25150 CE", as in the builder.

## Re-test: NEW-T50, NEW-T52, NEW-T53 (builder legs)

1. Builder, a new draft with 4 legs: click the bin on row 2. Expected: the row goes at once and "Leg removed. Undo"
   shows; Undo puts it back in row 2 with its values.
2. A draft with SELL 22800 CE: Add/Edit, pick SELL 22800 CE, Done. Expected: "Already in this strategy" with Increase
   quantity / Keep separate / Cancel, each clickable.
3. On a phone (or a browser window narrower than 640 px): Add/Edit. Expected: the drawer fills the screen and its own
   header row carries "Show Editor"; it returns to the editor. On a PC the tab stays on the drawer's edge.

## Re-test: NEW-T61, NEW-T64, NEW-T66, NEW-T67 (builder save and saved list)

1. Rename a saved strategy to an empty name; Save. Expected: "Give the strategy a name."
2. Saved tab, search "zzz". Expected: "No saved strategy matches zzz".
3. Saved tab, pencil on a row that is not open. Expected: it opens and the rename box follows.
4. Open `/strategy/builder?strategy=999999` (no such strategy). Expected: "This strategy was not found. It may have been
   deleted." and an "Open My Strategies" button; the button opens My Strategies.

## Re-test: NEW-T70, NEW-T71 (placeholders)

1. Open Orders. Expected: "Your broker orders, read-only. This page never takes an order."
2. Open any unbuilt page, e.g. `/home/important-alerts`. Expected: "The alerts that matter most will be collected on this
   page.", not "This page is a placeholder. It is built in a later work item."
3. `/settings/zerodha-connection` reads "Zerodha connection is not built yet." for now: its own sentence needs one line on
   the broker-name allow-list (the owner's edit; feature code never names the broker, ADR-012/ADR-029).

## Third batch (26 Nov evening): Lane T answers, D-51

| Item | Decision | State | What changed | Commit |
|---|---|---|---|---|
| T-Q5 Buy twice | owner, ADR-330 (40) | test corrected to the spec, PASS | the second Buy on a ticked contract removes the leg and unticks it; REQ-030 AC-5 says so | b92cd874 |
| T-Q4 Clear filters | coordinator (a) | spec corrected | REQ-029 AC-9: strike range and Details are view settings and stay | e329e82b |
| T-Q7 days left | coordinator (a), REQ-135 AC-2 | Fixed, not tested | the chain's "N days left" reads the server's `expiry_days`; the browser clock is no longer used (class: chain day counts from the browser clock 1 -> 0) | 025e15ee |
| T-Q8 Add Selected (0) | coordinator (a), ADR-328 (4) | Fixed, not tested | always shown, greyed, "Tick at least one contract to add."; U-Q12: with a tick but no Buy/Sell, "Choose Buy or Sell for each ticked contract." | 67cfebbe, 0836bb92 |
| T-Q9 30 spec-silent controls | coordinator (a) | spec lines written (table below) | 13 sentences in 9 REQs | 78790a40 |
| T-Q10 chain sentences | coordinator (a) | adopted, pending owner read | the chain's own sentences live in `lib/sharedStateText.js`; REQ-029 AC-12 lists them | b4dfb7c7 |
| D-51 Strategy Chart | owner, ADR-330 (43) | Fixed, not tested | the chart draws the strategy's open legs through one door `open_legs()` (backend/ofo_app/open_legs.py; the book today, Zerodha positions later), not the saved definition; a fully closed strategy: "This strategy has no open legs, so there is no strategy chart." (U-Q11, pending owner read); switch untouched | 53aaed67 |

## Re-test: T-Q7, T-Q8 (Option Chain)

1. Market > Option Chain near midnight or with the PC clock set a day off: "N days left" still matches the server's count.
2. Nothing ticked: "Add Selected (0)" shows greyed with "Tick at least one contract to add.".
3. Tick a contract without pressing Buy or Sell: greyed with "Choose Buy or Sell for each ticked contract."; press Buy: it turns blue.

## For the PC session: turn the Strategy Chart on (D-51, ADR-203, ADR-330 (43))

Reference: backend/ofo_app/held_switches.py:57-60 (`_is_on`): outside development/test the chart is on only when BOTH
variables are set. The app reads them from the process environment, else the `.env` file (ofo_app/config.py `app_env`,
same source as APP_ENV). So put the two lines in the server's `.env` (or the service's environment file):

```
OFO_HELD_STRATEGY_PRICE_HISTORY=1
OFO_HELD_STRATEGY_PRICE_HISTORY_REF=ADR-203
```

(`_TRUE` accepts 1/true/yes/on style values; the `_REF` must be non-blank and should name ADR-203, REQ-091 AC-7.)
Nothing in the repo sets them: no default or test environment was changed.

Restart: stop the backend (Ctrl+C in its window) and start it again the way you normally start it; the `.env` is read
when the app starts.

Check on a running paper trade after an exit:
1. Open a running paper trade (4-leg condor), Positions > Paper, and exit ONE leg (for example the SELL 22800 CE). Confirm it shows closed.
2. Open the trade in the builder (Live Strategies > its name) > Strategy Chart tab. The tab must draw a line, not "The strategy chart is not available."
3. The chart's legs must be the 3 still-open legs: the data call `GET /strategies/<id>/price-history` (browser Network tab) answers for the 3 open contracts only.
4. Exit the remaining legs one by one: after the last one the tab says "This strategy has no open legs, so there is no strategy chart." (U-Q11), and switching the two lines off again gives "The strategy chart is not available." (409).


## To file as deferred issues

None new after the coordinator's 17:17 rule (#750 and #751 were filed before it, with their stage rows).

## Spec lines for the 30 spec-silent controls (Lane T Q9 (a), coordinator 26 Nov)

For the owner to read in one place. Each sentence states today's behaviour in the REQ the control belongs to.

| Group | Controls (inventory ids) | Today's behaviour (file:line) | REQ / AC | Sentence added |
|---|---|---|---|---|
| Header keyboard | SHELL-01, SHELL-10 | AppHeader.vue:219-229 (Esc closes account/section menu, focus back), :147-166 (arrows, Enter/Space/Down open) | REQ-009 AC-9 | Esc closes header menus and returns focus; arrows move in a section menu; Enter/Space/Down opens |
| Log out | SHELL-09 | AppHeader.vue:347-355 (disabled, title says sign-in not built) | REQ-009 AC-10 | Log out is last in the account menu, shown greyed and does nothing |
| Not-found | NF-01 | NotFoundPage.vue:5-11 | REQ-009 AC-11 | Unknown address shows "Page not found" with one "Go to Home" link |
| Toast Dismiss | SHELL-13 | ToastHost.vue:23, useToast.js:13-40 (never expires, dedupe, max 5) | REQ-070 AC-8 | Toast stays until Dismiss/Open; one copy of an identical notice; at most five |
| Figure / tooltip / after-charges Esc | SHARED-08, BUILD-24, BUILD-34 | AfterChargesTap.vue:18,27; FigureHint.vue:51; Tooltip.vue:43 | REQ-136 AC-5 | Esc closes them; focus opens, second tap closes |
| Add/Edit, Show Editor, Show Strikes | BUILD-11, BUILD-15, BUILD-16 | StrategyBuilderPage.vue:1277, 1295 (drawer edge slot), 1298 (fixed left tab, pickerFolded) | REQ-080 AC-11 | Add/Edit toggles the picker drawer; Show Editor folds it; Show Strikes tab brings it back, picks kept (phone placement left to AC-10) |
| Modal / Drawer primitives | SHARED-11, SHARED-13, BUILD-139..143 | Modal.vue:30-62 (Esc, overlay, focus in/out, trapTab); Drawer.vue:48-54, 84, 91-126 | REQ-080 AC-12 | x, outside click or Esc close; focus moves in, Tab trapped, returns on close |
| Popover / depth Esc | BUILD-05, BUILD-88, BUILD-127 | StrategyBuilderPage.vue:1232; LegPicker.vue:706; DepthPopup.vue:44-50 | REQ-080 AC-13 | Esc closes View settings, picker settings and depth popup |
| Saved list and More menu | BUILD-146, BUILD-147, BUILD-159, BUILD-164 | SaveDraftBar.vue:65-71, 133, 436-455, 82-91, 502, 527 | REQ-134 AC-7 | "..." menu items, Esc closes; search by name or underlying; Show all link |
| Keep this level | SHARED-40 | PaperStops.vue:165-172, 228-231 | REQ-109 AC-11 | Row note plus button; stores level again; "Kept" / "Already kept" |
| Clear filters | CHAIN-10 | OptionChainPage.vue:190, 241; chainDisplay.js:57 | REQ-029 AC-11 | Resets five filters; expiry, strike range, Details stay |
| Learn links | LEARN-02, LEARN-04 | LearnPage.vue:46-54, 91, 128 | REQ-011 AC-3 | Detail view with Back to the list; title-only case-insensitive search |
| Broker Check again | BROKER-01 | BrokerSettingsPage.vue:69-80, 120 | REQ-015 AC-14 | Shown only when the check failed; re-reads the four statuses |

Notes: inventory rows BUILD-15 and BUILD-16 say "phone layout switch"; the code shows both tabs at every width (see defects in the report). Also edited docs/process/coverage-stages.yaml (REQ-015 AC-14 staged 4a) because coverage.py refuses to write without a stage per AC.

Seen while writing them: Log out is greyed and does nothing (REQ-009 AC-10 says so until sign-in is built); the builder saved-list search also matches the underlying (`SaveDraftBar.vue:84-85`, written into REQ-134 AC-7).
