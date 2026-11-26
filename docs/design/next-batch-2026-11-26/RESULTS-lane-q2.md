# Lane Q2 results (screens, Wave 2), 26 Nov 2026

Branch `feat/nb-screens-w2-1126`, cut from `origin/refactor/modular-doors` `db57d05`, then merged
`origin/fix/ic-live-test-1123` `f38630d` and `origin/feat/nb-screens-1126` `f6a1c8a` (merged base `83107be2`, gated and
pushed first). No PR. Paper only; no broker order endpoint is called; no migration. The highest status claimed for any
item is **Fixed, not tested**: the owner tests on his PC in market hours.

Standing-direction step: "iron-condor depth (freeze lifted 2026-11-26)" for new behaviour; step 4 item 10 for the defects.

Spec basis: ADR-330 (8), (10), (14), (15), (17) with the owner's 26 Nov answers; ADR-292, ADR-293 (1); ADR-201 (2)
(SPEC CHANGE, replaced by ADR-330 (10)); ADR-207; ADR-016 to ADR-019; ADR-008; ADR-003; ADR-281; ADR-320; ADR-321.
New wording is in REQ-070 (AC-7 and a body paragraph), REQ-081 and REQ-109 (body paragraphs, including the paragraph
"SPEC CHANGE (ADR-330 (10) replaces ADR-201 (2))"). No new decision row was written. ADR-201 itself is not edited: the
coordinator adds the superseded-by note (candidate row **ADR-NB-1**: "OD-1, one Positions list, supersedes ADR-201 (2)";
the plan's section 5 list item (6)).

## Per item

| Item | Status | Root cause (one sentence) | Class before / after |
|---|---|---|---|
| S-06 page wiring | Fixed, not tested | The builder page never passed `summary` to `SummaryCards`, so the basis line had no data. | 1 screen. Also fixed the Wave 1 quirk: the line is hidden when both max figures read "Not available". |
| S-14 Exit on the Live card | Fixed, not tested | The card had no Exit; Wave 1 waited for the refactor's exit door. | 1 card. Exit is a link to the Positions page (`?tab=paper&strategy=<id>&exit=<id>`) that opens the page's own confirm through `usePaperExit` + `ExitButton` + `PaperConfirmDialog`; the card holds no exit code. Hosting the composable would have copied about 80 lines of flow. Tier A review: REVISE, then PASS. |
| S-25 run-together number columns | Fixed, not tested | Table cells had no horizontal padding and headers were not aligned like their cells. | 9 tables without the shared class before, 0 after (one `.num-table` rule in `style.css`). A source-scan test fails on a table in these files without it. |
| S-01 bulk delete (ADR-330 (8)) | Fixed, not tested | New feature. | One route `POST /strategies/bulk-delete` runs the SAME `delete_draft` rule per id in its own savepoint; no second rule. Running paper strategies are deleted; the confirmation says how many are running. |
| S-03 wrong refusal for a held strategy | Fixed, not tested | `delete_draft` raised only `DELETE_AFTER_BASKET`, so a held strategy got "Orders were already sent". | Every refused row. After: one `_HELD_SQL` rule feeds both the list flag `held_at_broker` and the refusal reason; "This strategy is marked as held at your broker, so it cannot be deleted." |
| S-04 Rename under the mouse | Fixed, not tested | The confirm box replaced Delete inside the same action cluster, shifting Rename. | Every row confirm on My Strategies; the confirm is now its own full-width line below the row. The builder keeps its inline confirm. |
| S-05 bare "Loading..." | Fixed, not tested | No timeout and no retry on the list read. | My Strategies and Completed: skeleton, then after failure or 15 s "Could not load your strategies. Nothing was changed." with Retry. Not a speed fix. |
| S-02 ERR-6960F002 | **Open (not guessed)** | Not known without the owner's API log. | New measured fact (see Findings): `delete_draft` raises a raw database lock error (sqlstate 55P03) when another connection holds the row lock, which the route turns into ERR-xxxx. |
| Q2 one Positions list (ADR-330 (10)) | Fixed, not tested | New feature (SPEC CHANGE to ADR-201 (2)). | One list: filter All / Real / Paper (default All; `?tab=paper` gives Paper, `?tab=positions` gives Real, an `exit` link forces Paper); "PAPER" tag on every paper group, "REAL (Zerodha)" on every real group; two totals "Real P&L" and "Paper P&L", never summed; the second `/paper/strategies` read on the page was removed (PaperStrategies is the only paper reader and the only exit host). |
| Exit confirmation titles | Fixed, not tested | Titles were literals ("Exit paper positions", "Review paper orders"). | One door `positionKindWord` / `exitConfirmTitle` / `reviewConfirmTitle` in `lib/paperDrafts.js`: "Exit Paper positions", "Review Paper orders"; "Real (Zerodha order)" is built and tested but no real exit button exists (ADR-281). An unknown kind throws (fails closed). |
| S-28 Add orders on Completed | Fixed, not tested | The button was drawn for every group. | Completed groups show "Open in Builder" only. |
| S-23 fired stop stays "armed" | Fixed, not tested | PaperStops read its triggers once on mount. | 1 of 2 trigger readers was mount-only, 0 after; it re-reads on the list's good-read token, no new timer. |
| S-19 Stops panel without the index | Fixed, not tested | The panel asked for an index level and never read the index. | Reads `useIndexAnswer` (the strip's reader): "NIFTY now 25,735.00 as of 10:41:05", or "Index values unavailable." with no digits. |
| S-26 Stops panel jumps while typing | Fixed, not tested (cause structural) | Reason and status lines (`ce-reason`, `stop-reason`, error, saved) appeared and disappeared in the flow with no reserved height; measured in jsdom that inputs were never re-mounted. | Every such line is now in an always-rendered reserved slot; the form is keyed on strategy id. jsdom cannot measure pixels: the 16 px is confirmed only on screen. |
| S-15 screen half (ADR-330 (15)) | Fixed, not tested; **shows nothing until Lane P serves `closed_text`** | The total had no line saying it includes closed trades. | The screen prints the server's `closed_text` verbatim under the Paper total when served, never built in the browser. |

## Tests: red, then green

| Test file | Red before the fix | Green after |
|---|---|---|
| `frontend/tests/summary-basis-page-s06.test.js` (new) | 3 failed: "Cannot call text on an empty DOMWrapper" x2, "expected true to be false" | pass |
| `frontend/tests/paper-exit-link-s14.test.js` (new) | round 1: 1 failed; round 2: 7 failed (e.g. "expected '48' to be undefined") | 11 pass |
| `frontend/tests/number-tables-s25.test.js` (new) | 3 failed (rule missing, 9 tables, 18 headers) | pass |
| `frontend/tests/my-strategies-bulk.test.js` (new) | 15 of 16 failed | pass |
| `tests_app/test_strategy_bulk_delete.py` (new, DB) | 11 of 11 failed | 11 pass (local disposable PostgreSQL 16) |
| `tests_app/test_strategy_delete_app.py` (changed: held now expects the held sentence) | it asserted the old sentence | 31 pass |
| `frontend/tests/paper-stops.test.js` (changed) | 5 failed (S-23 "expected 'armed' to be 'fired'"; S-19/S-26 ids missing) | 32 pass |
| `frontend/tests/paper-completed-actions.test.js` (new) | 2 of 2 failed | pass |
| `frontend/tests/positions-one-list.test.js` (new) | 12 of 14 failed | pass |
| `frontend/tests/exit-title-door.test.js` (new), `chunk-c-round2.test.js` (new) | 5 of 5, 6 of 6 failed | pass |
| Changed with reason "ADR-330 (10) replaces ADR-201 (2)": `paper-tabs.test.js`, `positions-page.test.js`, `paper-list-4b.test.js`; pins "Exit Paper positions" / "Review Paper orders" in `builder-drafts-exit`, `paper-dialog-safe`, `paper-place-refresh`, `paper-exit-link-s14`, `exit-title-door` | | pass |

Guards: `one-door-screens.test.js` gained rule 5 (Positions files make no order calls and import no exit pieces; the
literal "Real (Zerodha order)" lives only in `lib/paperDrafts.js`; mutation checks failed the rule as expected); its
known bypasses are written above the rule. `leg-emitters-guard`, `test_paper_orders_one_door.py`,
`test_door_names_private.py`, `test_door_rebinding_and_asgi_scan.py` stay green.

## Known minors shipped (2-round limit reached)

1. A hand-typed URL with a duplicated `exit` parameter (`exit=48&exit=50`) opens the confirm for 48 (no POST without a click).
2. The try/catch round `router.replace` cannot catch a rejected promise; no router guard exists today, so unreachable.
3. The note "This strategy has no open paper legs to exit." also shows for an unreadable row and is not cleared by a later good read.
4. The held-with-a-plan DB test was written with its fix, not seen red first.
5. Bulk delete reads each selected row's revision with one GET per row (list rows carry no revision); a server `revision` on list rows would remove the N reads.

## Findings (for the coordinator)

- **S-02 candidate cause, measured:** with a second connection holding `FOR UPDATE` on a strategy row and `lock_timeout`
  300 ms, `strategy_store.delete_draft` raised `DBAPIError` (`LockNotAvailableError`, sqlstate 55P03); `_run` in
  `routes/strategies.py` re-raises non-store errors, so the user sees ERR-xxxx. The owner's case would be the 30 s
  `statement_timeout` (plan candidate (a)). No lock code changed. Candidate deferred issue: "a lock wait on delete ends
  as a raw 500, not a refusal sentence"; the reproducing DB test needs the admin engine for clean-up.
- **Worktree base:** helper worktrees made with isolation were cut from `main`, not from the lane branch, three times
  out of six; each brief now opens with a base check (`git merge-base --is-ancestor <base> HEAD`). Candidate harvest
  issue for the kit.
- **YAML in spec front matter:** a `\'` inside a single-quoted YAML scalar made REQ-070 unparseable; the builders'
  vitest checks read raw text and passed; `coverage.py` caught it. Fixed in `291e8055`.

## Owner questions

`docs/design/next-batch-2026-11-26/owner-questions-lane-q2.md`: LQ2-1, "Real P&L" has no server figure
(`/positions` returns units only); built meanwhile: a dash with "Real P&L is not shown yet: the server does not price
Zerodha positions."

## Owner screen-check list (paper only, market hours; Ctrl+F5 first)

1. **S-06.** Open a strategy in the Strategy Builder that has never been placed.
   - Expected: under Breakeven, the line "Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges."
   - Open a placed paper strategy. Expected: the line appears once, not twice.
2. **S-14 Exit.** Open Live Strategies. On a running paper strategy's card, click "Exit".
   - Expected: Current positions opens with the Paper filter on, and the confirmation titled "Exit Paper positions" opens for that strategy's open legs.
   - Click Cancel. Expected: nothing is sent; the dialog does not come back by itself after a few seconds.
   - Expected: a Completed strategy's card has no "Exit".
3. **S-25.** Open a placed paper strategy in the builder. Check the Orderbook, the net positions table, the closed rows, and the payoff / greeks tables under the chart; then a Live card's leg table.
   - Expected: every number column (e.g. Qty 65 and Price 101.20) is visibly separate and sits under its own header.
4. **S-01 bulk delete.** Open My Strategies.
   - Tick two rows. Expected: the button reads "Delete selected (2)".
   - Type in the search box, then click "Select all N shown". Expected: only the rows still shown are ticked.
   - Tick rows including one Running paper strategy and click Delete selected. Expected: "Delete N strategies? 1 of them are running." (the exact count).
   - Confirm. Expected: a result line such as "3 deleted"; any kept row is named with its reason.
   - Click Undo. Expected: every deleted strategy is back in the list.
5. **S-03.** Find a strategy marked held at your broker (e.g. Held IC k10).
   - Expected: it has no tick box and shows "This strategy is marked as held at your broker, so it cannot be deleted." (not "Orders were already sent").
6. **S-04.** On any row, click Delete without moving the mouse.
   - Expected: the confirmation opens as its own line below the row; Rename stays where it was and the mouse is not over it.
7. **S-05.** Reload My Strategies.
   - Expected: grey placeholder rows while it loads, never a bare "Loading...". If the read fails: "Could not load your strategies. Nothing was changed." with Retry.
8. **Q2 one list.** Open Current positions.
   - Expected: no Paper tab; three buttons All / Real / Paper with All selected; paper strategies each tagged "PAPER"; at the top two totals "Real P&L" and "Paper P&L" and no third figure.
   - Expected: "Real P&L" shows a dash with "Real P&L is not shown yet: the server does not price Zerodha positions." (LQ2-1).
   - Click Real. Expected: paper rows disappear; Paper P&L stays at the top. Click Paper. Expected: only paper rows.
   - From the builder's compact paper list, click its "Current positions" link. Expected: the page opens on Paper.
   - With no Zerodha positions open, Expected: the real part reads "No open Zerodha positions." and the paper rows still show below.
9. **Exit title.** On a running paper strategy, click Exit. Expected: the title reads "Exit Paper positions".
10. **S-28.** Tick "Show closed positions" if needed and find a Completed strategy.
    - Expected: only "Open in Builder", no "Add orders". A Running one still shows both.
11. **S-23.** Arm a leg stop on a running paper strategy close to the live price; wait until it fires (the leg closes).
    - Expected: within one refresh (about 5 s), without reloading, the Stops panel row reads "fired", not "armed".
12. **S-19.** Open the Stops panel. Expected: a line "NIFTY now <value> as of <time>" equal to the index strip at the top of the page; with the feed down, "Index values unavailable." and no number.
13. **S-26.** In the Stops panel, type a level slowly (e.g. 24500.07) while prices update.
    - Expected: the boxes do not move up or down while the reason line under them appears or changes.
14. **S-15.** Not visible yet: it waits for Lane P's `closed_text`. After that merge, a line "Includes N closed strategies ..." shows under the Paper P&L total.
