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
| NEW-T51 | Builder | product question U-Q4 | expected-fail kept until answered | "Pick from Option Chain" opens the picker's strike view by design (W-195 review 7) | - | - |
| NEW-T52 | Builder | defect, fix now | Fixed, not tested | Modal and Drawer were both `z-50`; the later-mounted drawer covered the dialog | dialogs that open under a drawer: 7 -> 0 (Modal primitive) | 80049722 |
| NEW-T53 / NEW-T68 | Builder (phone) | product question U-Q5, option (b) built | Fixed, not tested | The 520 px drawer pushed its edge tab past a 390 px screen | drawers whose tab leaves a phone screen: 1 -> 0 (Drawer primitive) | 572c568f |
| NEW-T60 | Builder | defect, deferred + question U-Q6 | expected-fail kept; issue #751 | REQ-154 not built; ADR-329 (3) is the newer rule | - | - |
| NEW-T61 | Builder | defect, fix now | Fixed, not tested | The catalogue text was "The strategy has no name." | empty-name texts differing from REQ-134 AC-1: 1 -> 0 | 359af7db |
| NEW-T62, NEW-T63 | Builder | defect, deferred | expected-fail kept; issue #750 | REQ-138 not built (needs server storage: a migration) | - | - |
| NEW-T64 | Builder | defect, fix now | Fixed, not tested | The saved list printed its own literal instead of the shared `noMatchText` | 1 -> 0 | 359af7db |
| NEW-T65 (N-13) | Builder | already fixed on base | PASS, mark removed | Lane R | - | 1bf1a4d2 |
| NEW-T66 | Builder | product question U-Q7, built in part | Fixed in part, not tested | A bare 404 carried no catalogue parts, so the page showed the connection line | bare-404 callers showing the connection line: all -> 0 (shared `mapError`) | af807755 |
| NEW-T67 | Builder | defect, fix now | Fixed, not tested | `renameRow` cleared its pending id before the async open finished | 1 -> 0 | 359af7db |
| NEW-T70 | Orders placeholder | defect (observation), fix now | Fixed, not tested | The note described the old strategy-linked scope | 1 -> 0 | 5d3a1f91, 9d485211 |
| NEW-T71 | Placeholders | defect (observation), fix now | Fixed, not tested | One developer sentence on every placeholder | 15 -> 0 (`COMING_LINES` in nav.js, REQ-009 text; "your broker" wording per the broker-name guard; one page on the fallback line pending an allow-list line) | 5d3a1f91, 9d485211, 23ec7b9a |

Detection: the un-marked Lane T tests are the detection for each class, plus `frontend/tests/api-unreadable-body.test.js`
(the shared client's rule) and EXIT-6b (Cancel keeps the ticks). Spec text changed: REQ-009 (wording of unbuilt pages),
REQ-030 AC-15 (the leg Undo), catalogue `strategy_name_empty`.

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
3. On a phone (or a 390 px browser window): Add/Edit. Expected: "Show Editor >>" is visible at the right edge; it
   returns to the editor.

## Re-test: NEW-T61, NEW-T64, NEW-T66, NEW-T67 (builder save and saved list)

1. Rename a saved strategy to an empty name; Save. Expected: "Give the strategy a name."
2. Saved tab, search "zzz". Expected: "No saved strategy matches zzz".
3. Saved tab, pencil on a row that is not open. Expected: it opens and the rename box follows.
4. Open `/strategy/builder?strategy=999999` (no such strategy). Expected: "The page or action you asked for is not
   available here." (not the connection message).

## Re-test: NEW-T70, NEW-T71 (placeholders)

1. Open Orders. Expected: "Your broker orders, read-only. This page never takes an order."
2. Open any unbuilt page, e.g. `/home/important-alerts`. Expected: "The alerts that matter most will be collected on this
   page.", not "This page is a placeholder. It is built in a later work item."
3. `/settings/zerodha-connection` reads "Zerodha connection is not built yet." for now: its own sentence needs one line on
   the broker-name allow-list (the owner's edit; feature code never names the broker, ADR-012/ADR-029).
