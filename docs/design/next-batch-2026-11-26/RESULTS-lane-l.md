STATUS 21:00 | item 4 (62), UX-05, UX-06 built; AF-07 covered; earlier items pushed d94ca71 | final gate and push next | blocker: none

# Lane L: P&L totals and list counts (27 Nov 2026)

Highest status: **Fixed, not tested**. Nothing is approved until it passes on the owner's PC.

## Core: which trades does each of the five totals read? (from the code)

| Place | Reads | Trade set | Engine call |
|---|---|---|---|
| Home "Total P&L" | `GET /paper/strategies` `totals.totalAfter` (lib/paperPnl `usePaperPnl`, its own read on mount and every refresh tick) | rows NOT expired-open and able to be priced (`_priced`); a settled/closed row counts at its booked result; a settling or unpriced row is left out and counted | `paper.py` list route: `_priced` then `_totals` then `book_totals` / `sum_after_charges` (ofo.engine, ADR-008) |
| Positions "Paper P&L" | same `totals.totalAfter` (PaperStrategies' own read, passed up by `@summary`) | the SAME set | the SAME call |
| Live Strategies card | `g.totalAfter` of ONE strategy from the same list read (lib/paperPnl `cellFor`) | that one trade | the same list route, one row |
| My Strategies row | same as Live card | that one trade | same |
| Builder TOTAL row | `GET /paper/strategies/{id}` book, `sharedTotal` | that one trade | the book route (same engine functions) |

Finding: by the code, Home and Positions read the identical server set; there is no second trade set and no money formed in a page. The only mechanism I can find for two totals to differ "in the same minute" is that they are two separate reads at two instants (Home read on its mount/tick, Positions on its own), which differ while prices move. With the market closed (frozen prices) they must agree to the paisa. **I could not reproduce a different-trade-set disagreement**, so no code fix is made for item 1 and none is claimed. Proof test (passes, documents the one set): `frontend/tests/paper-totals-one-set.test.js` (Home and Positions show the same figure for the mixed set and for the paused state) and `tests_app/test_paper_totals_lines.py::test_core_*` (running +15, settled +40, settling no price: total 55 over the first two, the third counted).
If it still differs on the PC while CLOSED: write down both figures and the "Includes/left out" lines of each page; that points to a different reply, which this code cannot produce.

## Item 2: counts (fixed, not tested)
- "Select all 16 shown" over 17 rows: the label counted only the rows that can be ticked. Now `selectAllText(selectable, shown)` (lib/strategyActivity.js) gives "Select all 16 of the 17 shown" when they differ, "Select all N shown" otherwise; both numbers come from `visible`, the list under it. Tests: `frontend/tests/my-strategies-bulk.test.js` (new describe, 17 rows / 1 not deletable; and the plain case).
- "Includes N closed strategies" vs the rows (15 vs 14): the server count and the rows could not be tied. Now `readPaperList` compares the server's `closed_count` with the closed rows of the same reply; if they differ the line is NOT shown (fail closed) and `closedMismatch {server, rows}` is set. With an unreadable row, or no count sent, the server line stands as sent. Tests: `paper-totals-one-set.test.js` (4 cases). I could not find where the 27 Nov 15 vs 14 came from (no data here); the server and client predicates are the same (no open leg, or EXITED). The Completed Strategies page itself shows no count except the Select all label.

## Item 3: states of the two lines (built)
`tests_app/test_paper_totals_lines.py`: none left out, one left out unpriced, one settling (left out, total unchanged), expired + unpriced together, plural closed, nothing priced (blank total). Pure, no database; the DB route tests already existed (`test_paper_totals*.py`).

## Item 4: after-close dash (owner question, nothing changed)
Decided behaviour: ADR-324 (3) and ADR-330 (35): "when none can be priced the total is blank with its reason". Today a settled trade (+40 booked) with only unpriced running trades gives a dash with "Paper P&L paused - prices not live". Pinned by `test_item4_*`.
**Owner question** (the two readings clash): ADR-330 (35) text "Not chosen: also count a settled or settling trade at its booked result; keep the blank total." versus the weekend brief "a settled trade counts in the Paper total at its booked result". Recommendation: when no running trade can be priced but settled trades exist, show their booked sum with the line "N strategies left out: their prices are not live." instead of a dash (the booked result is a fact, not a price). Not done: needs the owner's yes.

## Paper-only path found
None new. (The Today total, D-68, excludes scenario strategies: existing, not mine.)

## Pending owner read (new on-screen sentence)
- "Select all {n} of the {m} shown" (My Strategies / Completed Strategies, only when some rows cannot be ticked).

## To file as deferred issues
- Home and Positions are two independent reads: add "as of HH:MM:SS" to both totals so a difference in the same minute can be explained (needs owner wording).
- Server could send the closed-row ids so the page ties the count by id, not only by number.

## Screen steps for the owner's PC (expected figures)
(a) Market CLOSED (frozen prices): open Home, note "Total P&L" (say X); open Positions, note "Paper P&L" with its "(after charges)" label: equal to X to the paisa. Open Live Strategies and My Strategies: the sum of the rows listed with a figure plus the settled ones equals X unless the line "N strategies left out" says otherwise. Tick "Show closed positions": the number in "Includes N closed strategies" equals the number of closed rows listed; if not, the line is hidden (by design). Completed Strategies: with a held-at-broker row, the label reads "Select all N-1 of the N shown".
(b) Monday live, same minute: reload Home then Positions within 10 seconds; figures may differ by one price tick (two reads); more than a tick is a defect: send both figures and the minute.

## Tasks / model / minutes
| task | model | minutes |
|---|---|---|
| read code, table, build items 2 and 3, tests | Sonnet (this session) | ~70 |
| independent review of totals change (money figures) | Opus (reviewer), Why Opus: money figures | ~15 |

## Added by the coordinator (after the first push)
- UX-32 (cards keep old numbers): `usePaperPnl` (Home, Live, My Strategies) now re-reads /paper/strategies when the window is focused or the tab becomes visible, not only on the timer. Test: `paper-totals-one-set.test.js` (UX-32). Screen step: open Home, change a trade in another tab, return to the Home tab: the Total P&L updates within a second without a reload. Fixed, not tested.
- AF-07 (Real total while Zerodha is disconnected): already pinned by `frontend/tests/positions-one-list.test.js` (refused read: "-" plus the server's reason, no earlier figure; the page reads /positions once, keeps nothing). PC check this weekend: Positions with Zerodha disconnected shows "-" and the connect sentence under Real P&L.
- File owners: I did not edit routes/paper.py or PaperStrategies.vue. Page change needed for Lane V (optional): show `closedMismatch` (set in readPaperList) as a short reason under the Paper total when the closed line is hidden.

## Opus review (Why Opus: money figures)
PASS, four minor findings, none fixed (see To file): the tie compares the count, not the sentence; an unreadable row or malformed count lets the server line stand; no page reads `closedMismatch`; the pure test copies the route's closed predicate instead of calling it.

## Gate
Run 1: TOTAL FAIL only because this container had no origin/main (ci_checks merge-base, app_tests git diff). Run 2 on b303411 (after `git fetch origin main`): TOTAL PASS (marker written), pushed.

Run 3 on d94ca71: TOTAL PASS, pushed (UX-32 and RESULTS).

## Item 4 built (ADR-330 (62), owner 27 Nov evening): Fixed, not tested
- `routes/paper.py::_priced(..., booked_alone=True)` for the HEADER total (Home, Positions): when no running trade can be priced but closed/settled trades have a booked result, the total is that result, with the closed line and the (35) count line; blank with its reason only when nothing at all can be priced. A settling or expired-open trade stays left out and counted. Decimal, one engine; the page only prints. (Lane K's push was merged first: origin/fix/order-limits-1127.)
- Tests first (failed, then passed): `tests_app/test_paper_totals_lines.py` (`test_item4_*`, 4 cases) and, on a throw-away PostgreSQL 16 here, 5 existing DB tests in `tests_app/test_paper_totals.py` that pinned the old blanking rule, now pinned to (62) (names changed; 22 pass). Also pass on it: test_paper_totals_closed, test_paper_closed_rows, test_d68_today_total.
- Opus review 2 (Why Opus: money figure): REVISE, one MAJOR: the Today total (D-68) shares `_priced` and has no left-out line on screen, so (62) would have shown a figure with no line. Fixed: Today keeps its old rule (`booked_alone` False; test `test_item4_the_today_total_keeps_its_own_rule...`). Minor F2 (two assertions dropped, two names stating the opposite) fixed. Not covered by the reviewer: a settling trade priced after 15:30 under ADR-330 (36) (unchanged by this diff).
- Owner question for later: should Today follow (62) too? It needs a left-out line in the Today block (page change for Lane V, `readToday` ignores `left_out_text`).
- For Lane K: after merging origin/fix/order-limits-1127, `tests_app/test_paper_routes.py::test_a_bad_price_is_422_with_the_reason_and_nothing_is_stored[0]` and `[-5.00]` fail (they expect "a multiple of 0.05"; K's zero-price refusal says "Type a price above 0 ..."). Not my change; K to update the test.
- Environment: `test_adjustment_history_why.py::...` fails with or without my change (pre-existing, StopIteration).

## UX-05 and UX-06 (Lane O's handover), Fixed, not tested
- UX-05 `MyStrategiesPage.vue`: while the list is being re-read (after Undo), "Loading your strategies..." replaces "No saved strategy matches ..." and "No strategy ...". Test `my-strategies-bulk.test.js` (UX-05).
- UX-06 `CreateStrategyPage.vue` (the button is there, not in MyStrategiesPage; no other lane's list names it): "Show strategies" is grey with a reason under it. Test `create-strategy.test.js` (UX-06).
- Pending owner read (new sentences): "Loading your strategies..."; "Choose an expiry first."; "Waiting for the contracts to load."; "Waiting for the index price."; plus "Select all {n} of the {m} shown" from before.
- Screen steps (market CLOSED fine): My Strategies, delete a saved strategy, search a part of another name, press Undo: until the list answers the line reads "Loading your strategies...", then the row is back (no "No saved strategy matches"). Create Strategy > guided > pick "I know the strategy": "Show strategies" is grey with "Choose an expiry first."; pick an expiry: it turns normal and the line goes. Item 4 (market CLOSED, after 15:30 with a settled trade and only unpriced running ones): Home "Total P&L" shows the booked sum, Positions "Paper P&L" the same, with "Includes N closed strategies." and "N strategies left out: their prices are not live."

SAFE TO CLOSE once the final push below is confirmed.
