# Lane Q Wave 1 results (26 Nov 2026)

Branch `feat/nb-screens-1126`, cut from `origin/fix/ic-live-test-1123` at `e01f747`. No PR. Paper only, frontend only.
The highest status claimed is **Fixed, not tested**: the owner tests on his PC in market hours.

Spec basis: ADR-207, ADR-068, ADR-321 (2) and (3), ADR-003, ADR-008. New wording is in REQ-008, REQ-109 and REQ-081
(appended body paragraphs). No new decision row is needed, so no ADR-NB placeholder.

## Per item

| Item | Status | Root cause (one sentence) | Class before / after |
|---|---|---|---|
| S-18 Home "Recent strategies" link | Fixed, not tested | `HomeOverviewPage.vue:121` linked to `/strategy/builder` with no `strategy` query, so the builder opened on no strategy. | Builder links that should carry an id but did not: 1 before, 0 after. The new helper `lib/strategyLinks.js` `builderLinkOf` is used by Home and the Live card. Five correct hand-built copies remain in other lanes' and Wave 2 files: `PaperStrategies.vue:232,:350`, `MyStrategiesPage.vue:96`, `SaveDraftBar.vue:411`, `AdjustCompare.vue:17`. |
| S-14 Live card name / Stops / header | Fixed, not tested (Exit part waits) | The card's title was plain text, and the entry column header was the literal "Planned entry" whatever the strategy's state. | 1 card. Exit waits for the refactor's `ExitButton` (Phase 4); a test pins that no Exit link exists yet. |
| S-25 Orderbook Qty / Price | Fixed, not tested | The order table's cells had no horizontal padding, and the Qty/Price headers were centred over right-aligned cells, so "65" and "101.20" touched. | Tables with unpadded adjacent right-aligned number cells: at least 9 (hand-picked grep, a lower bound). 1 fixed (order-table). Still open: PaperBookPanel net-table `:54-58`, `ClosedRows.vue:13-15`, `LowerCard.vue:70-80`, ChartCard step / payoff / compact / greeks tables (`:180-199`, `:214-226`, `:247-256`, `:314-326`), `LiveStrategyCard.vue:240-249`. Candidate deferred issue (coordinator files). |
| S-06 Plan summary basis line | **PARTIAL, page wiring waits Wave 2** | The only basis line (`StrategyBuilderPage.vue:1175` `tiles-basis`) shows for a placed paper book only, so an unplaced plan's summary never says that Max Profit/Loss are after charges and breakevens before. | 1 screen. The card part is built and tested: `SummaryCards.vue` has an optional `summary` prop and prints `summary-basis`. The sentences have one home in `targetBlock.js`, and the old `OPEN_LEGS_ONLY_*` texts are derived from them and asserted byte-identical. It shows nothing until `StrategyBuilderPage.vue` passes `:summary="data.summary"` at about line 1176. That page is a Wave 2 file (the refactor changes 258 lines of it), so Wave 2 makes this one-line edit. |

Fix choice for S-06: the label, not after-charges breakevens. Reason: `ofo/scenario/levels.py` and `ofo/outcome/` are in the Tier A `SAFETY_SET` (`scripts/orchestrator/safety_set.py:10`). The plan called Q4 Tier B; that was a class 1 card defect. The coordinator's scope words also ask to "say which figures are before and after charges". The engine option is owner question LQ-1 in `owner-questions.md`.

Verified premise: the plan summary's Max Profit / Max Loss include charges whenever `summary.charges` is not null (`backend/ofo/outcome/service.py:526-527`).

Known quirk (not fixed): a mixed-expiry plan sends `charges` while its max figures read "Not available", so the line would say "after charges" over "Not available".

Detection change: the class-level homes are `builderLinkOf` (one link maker) and the one basis-sentence home. The guard is the new tests. No detection change: no repo-wide scan exists for hand-built builder links, and adding one would flag five correct copies in files this lane may not edit.

Facts in the plan or brief that were false: (1) Q4 is Tier A, not Tier B (above). (2) `SummaryCards.vue` had no `summary` / `charges` prop, so the fix needs a page edit. (3) `PaperBookPanel.vue` is also edited by `refactor/modular-doors`, in other hunks; the order-table lines do not overlap.

## Tests: red, then green

| Test file | Red before the fix | Green after |
|---|---|---|
| `frontend/tests/home-open-strategy.test.js` (new) | `Failed to resolve import "@/lib/strategyLinks"` | pass |
| `frontend/tests/live-card-links-s14.test.js` (new) | `Unable to get [data-testid="live-strategy-open"]`, `... live-strategy-stops`, `expected 'InstrumentLotsPlanned entryLTP' to contain 'Entry price'` | pass |
| `frontend/tests/summary-basis-s06.test.js` (new) | `Cannot call text on an empty DOMWrapper` (x2), `expected undefined to be 'Max Profit and Max Loss are after cha…'` | pass |
| `frontend/tests/orderbook-columns-s25.test.js` (new) | `<th class="text-left font-normal">Time</th>: expected false to be true` | pass |
| `frontend/tests/home.test.js` (changed) | It asserted the bug: every recent link was a bare `/strategy/builder`. It now expects `?strategy=<id>`. | pass |

Lane run on 26 Nov: 11 files, `Test Files 11 passed (11)`, `Tests 132 passed (132)`; eslint clean on the changed files.

## Owner screen-check list (paper only, market hours)

1. **S-18.** Fresh page load (Ctrl+F5) of Home. Under "Recent strategies", click "Open in Strategy Builder" on the second row, not the first.
   - Expected: the address bar ends in `/strategy/builder?strategy=<that row's id>`.
   - Expected: the builder shows that strategy's name and legs.
2. **S-18 repeat.** Go back to Home and click the first row.
   - Expected: the first row's strategy opens, not the one opened in step 1.
3. **S-14 name link.** Open Live Strategies.
   - Expected: each card's name is a link.
   - Click a running paper strategy's name. Expected: the builder opens on that strategy.
4. **S-14 Stops link.** On the same card, click "Stops".
   - Expected: Current positions opens on the Paper tab for that strategy.
   - Expected: a Completed strategy's card has no "Stops".
5. **S-14 header.** On a running paper strategy's card, check the leg table.
   - Expected: the column is headed "Entry price".
   - Expected: each value equals that leg's average price on the Positions page. If it does not, see LQ-2.
   - Expected: a draft (never placed) reads "Planned entry".
6. **S-25.** Open a placed paper strategy in the builder and switch the paper panel to Orderbook.
   - Expected: Qty (e.g. 65) and Price (e.g. 101.20) are visibly separate columns, both right-aligned under their headers.
7. **S-06.** Not visible yet: it waits for the Wave 2 one-line page edit. After Wave 2, an unplaced plan's summary shows the line "Max Profit and Max Loss are after charges estimated at entry prices; breakevens are before charges." under Breakeven.

## Not done / parked

- S-06 page wiring: waits Wave 2 (`StrategyBuilderPage.vue`).
- S-14 Exit: waits refactor Phase 4 `ExitButton`.
- S-25 class: 8 more tables (list above). Each is in a file outside this item's scope or in a Wave 2 hunk. Candidate deferred issue.
- Moving the five hand-built builder links onto `builderLinkOf`: Wave 2 / other lanes' files.
