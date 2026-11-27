# Lane TD: browser walk of builder, stops and dialogs (11 items)

STATUS: 03:50 IST 28 Nov, all 11 items walked: I-71 FAIL (defect), I-21, I-41, I-66, I-86, I-88 PARTIAL (order-dependent steps BLOCKED), I-20, I-72, I-78, I-79, I-93 PASS. Push BLOCKED by the pre-push gate (see "Push gate").
Branch test/r2-walk-builder-1128 (from integration/weekend-1127 + integration/conflicts-1127 16c536f0). Paper only, no broker.

## Set-up as run (decided, not asked)
- PostgreSQL 16 (`pg_ctlcluster 16 main start`), database exactly `ofo_dev`, roles as in app-tests.yml, migrated to `0059_last_close (head)`.
- Python deps from requirements-app.txt; frontend `npm ci && npm run build`; `vite preview` on 4173 (/api -> 127.0.0.1:8000), second preview on 4174 with `OFO_API_TARGET=http://127.0.0.1:9` (closed port).
- Catalogue: ofo_dev had no contracts, so `seed_scenario.py ADJ-02` refused ("0 live catalogue contracts for NIFTY 22500 PE 2026-11-09"). Loaded the scenario's own instrument rows through the guarded loader `catalogue_load.run` with as_of = scenario day (script `tests_browser/r2_1128_d/load_cat.py`), then `python scripts/seed_scenario.py ADJ-02` -> "ADJ-02 strategy id 1".
- Clock: the catalogue routes judge currency on the real database clock (2026-11-27), so with APP_ENV=development the 9 Nov contracts read as expired and the builder showed "This strategy's paper position could not be read, so it is not shown. Try again." (all API answers were 200; the catalogue answered 0 contracts). Fix of the set-up, not of the product: API started with `APP_ENV=test TEST_CATALOGUE_DATE=2026-11-06 OFO_SCENARIO=ADJ-02` (the test pin the code provides; scenario mode allows `test`). Dummy broker settings (KITE_*, BROKER_TOKEN_KEY) because the app refuses to start without them; nothing connects.
- Browser: Playwright + preinstalled Chromium, 1366x768, JPEG screenshots in `screens-td/`.

## Per item

Build head: 7583668d plus the walk files (integration/weekend-1127 + integration/conflicts-1127 16c536f0). Scenario ADJ-02 (strategy 1) unless said. Machine clock was UTC 21:40 to 22:15 on 27 Nov (03:10 to 03:45 IST 28 Nov); the scenario clock reads 6 Nov 11:40 IST.
Scripts: `tests_browser/r2_1128_d/*.js` (run: `NODE_PATH=$(npm root -g):frontend/node_modules node tests_browser/r2_1128_d/<file>.js`); screenshots in `screens-td/`.

| Item | Result | Evidence |
|---|---|---|
| I-20 API stopped: grey Exit, reason line, dialog, builder empty | PASS | i20_outage.js, i20-0x*.jpg |
| I-21 exit blocked by a contract with no price; "Keep this level" | PARTIAL: block sentence PASS; "Keep this level" BLOCKED | i21.js, i21-0x*.jpg |
| I-41 builder money figures | PARTIAL: table total, D-11 tiles, D-14 PASS; re-buy steps BLOCKED | i41_i79.js, i41_table.js, i41_d14.js |
| I-66 trade changed elsewhere | PARTIAL: name PASS; tag change BLOCKED | i66.js, i66-0x*.jpg |
| I-71 Pick from Option Chain | FAIL (defect D-TD-1) | i78_i71.js, i71-0x*.jpg |
| I-72 top-menu items | PASS (19 of 19) | i72.js |
| I-78 Rename + Esc | PASS (outcome reads as nothing) | i78_i71.js, i78-0x*.jpg; vitest rename-paper-d65 6 passed |
| I-79 Greeks tab | PASS | i41_i79.js, i79-01-greeks-tab.jpg |
| I-86 lists with API down; Retry | PARTIAL: message on all 10; Retry exists on 2 of 10 (D-TD-2) | i86_lists.js, i86-*.jpg; vitest d38-timeouts-pages 3 passed |
| I-88 wording, labels, View button (ADR-330 (30)) | PARTIAL: View, D-52, D-58 zero-price PASS; D-54 Delete and D-58 quotes/time-exit/raw key BLOCKED | i88.js, i88-0x*.jpg |
| I-93 Stops side by side; scroll after Save | PASS | i93.js, i93-0x*.jpg |

## I-20 (T1-21 steps 1, 2, 4, 6)
Exact text, in order (`i20_outage.js`):
- API up, nothing ticked: `Exit (0)`, disabled, reason `Tick a leg to exit.`
- Leg `NIFTY 9 Nov 22500 PE` ticked: `Exit (1)`, enabled, no reason line (i20-01).
- API stopped, 12 s later: `Exit (1)`, disabled (cursor not-allowed, opacity 0.5), reason `Prices are not live; try again when they update`. Leg rows show dashes for price and P&L; the totals read `Paper P&L paused - prices not live` four times (i20-02).
- API started, 15 s later: `Exit (1)` enabled again, the tick was kept (i20-03).
- Exit clicked, dialog: `Exit Paper positions S Exit NIFTY 9 Nov 22500 PE Lots Price about 0.85, as of 11:39:59, the server sets the exit price when you confirm ... After these orders, maximum loss: -20,273.50 before, -29,45,163.00 after. ... This is not a real trade. Paper orders use no real money. Cancel Confirm` (i20-04).
- API stopped with the dialog open, 14 s later: the dialog STAYS open and gains the line `NIFTY 9 Nov 22500 PE: Prices are not live; try again when they update` (i20-05). T1-21 expects "closes by itself" only for Monday's step 3 (live prices). After the API is back the dialog is still open and Exit (1) is enabled (i20-07).
- Builder opened while the API is down (new tab): `This strategy's paper position could not be read, so it is not shown. Try again.` with the four-part block, then `The page could not get an answer from the server.`; the Saved Strategies pane reads `Coming soon: Positions Open positions` (i20-06). Builder with no strategy on the second preview (/api to a closed port): `No legs yet`, `Pick from Option Chain`, `The page could not get an answer from the server.` (i20-dead-preview-builder).
- O-1: T1-20 expects `Paper P&L paused - prices not live, as of <date>, <time> IST`; the screen shows no "as of" (Positions totals, Home).
- O-2: the dialog's `-20,273.50 before, -29,45,163.00 after` mixes plain and lakh grouping in one sentence; the jump is the naked short put left after the long put is exited.

## I-21
Scenario ADJ-02a (a git-excluded copy of ADJ-02 made by `make_null_ltp.py`, the 23500 CE chain row has ltp null; strategy 2).
- Positions card: `Paper P&L paused - prices not live`, `No price for: NIFTY 9 Nov 23500 CE.`, `Maximum profit and maximum loss are before charges and taxes: the charges could not be priced.`
- Builder net row: `NIFTY 23500 CE 2026-11-09 2 42.00 - 0.00 - - Exit`; its Exit is enabled.
- Tick only that leg: `Exit (1)` stays blue (not grey). Click: dialog `Exit Paper positions B Exit NIFTY 9 Nov 23500 CE Lots Price the server sets the exit price when you confirm Checking whether this exit leaves a sold option without protection... NIFTY 9 Nov 23500 CE: Prices are not live; try again when they update Cancel Confirm`; Confirm is disabled (i21-02, i21-06). The builder row's Exit gives the same sentence (i21-05).
- O-3: the sentence says "Prices are not live" although only one contract has no price; the button is not grey beforehand, the block shows only inside the dialog.
- "Keep this level": BLOCKED. The button exists only for an armed stop with `set_before_adjustment` (backend/ofo_app/routes/paper.py:1820, 1916), which needs a paper order placed after the stop; scenario mode refuses orders (409) and `paper_triggers` is guarded (UPDATE of created_at refused: "only fired_at and cancelled_at of a paper trigger may change"). Unit test frontend/tests/paper-stops.test.js: 37 passed. Needs Monday's live window.

## I-41 (T1-14)
ADJ-02 (strategy 1), exact text:
- Left strip: `Total P&L (after charges) -1,836.71`, `Charges paid ₹117.65`, `Estimated cost to close ₹107.06`, `Checked at 11:40:00 IST`, `0 pending changes`. The rows add up: -2,717.00 + 5,083.00 - 5,473.00 + 1,495.00 = -1,612.00; minus 117.65 and 107.06 = -1,836.71.
- P&L Table total row: `Charges paid ₹117.65 Estimated cost to close ₹107.06 Total ₹44.05 credit ₹56.45 credit -1,836.71 (after charges)`.
- Tiles: `Max Profit (after charges) +5,501.79`, `Max Loss (after charges) -20,498.21`, `Breakeven 22,658 (-3.3%), 23,542 (+0.5%)`, `Profit left +7,338.50 includes Rs 1,836.71 needed to recover the current loss`, `Loss left -18,661.50`.
- Add Booked P&L off (booked is 0 here): `+5,500` / `-20,500`, breakeven `22,656 (-3.3%), 23,544 (+0.5%)`.

ADJ-13 (strategy 3, booked +962; i41-adj13-*.jpg): switch ON `Max Profit +4,823.72`, `Max Loss -21,176.28`, `BE 22,863 (-1.7%), 23,487 (+1.0%)`; switch OFF `+3,967`, `-22,033`, `BE 22,868 (-1.6%), 23,482 (+1.0%)`. So the D-11 tiles DO change with the switch now. The table total row reads `-2,332.79 (after charges)` in BOTH states, compact and full view: the table total does not move with the switch (it always includes booked). That is the "table total not visibly changing" of the 27 Nov note; the spec does not say whether it should move (O-4).
- O-4: switch OFF shows whole-rupee figures (`+3,967`, `-22,033`, `+5,500`) where ON shows paise; the note above the tiles becomes `Open legs only: the booked P&L is not included...`. Owner to say if the rounding is intended.
- D-14 (ADJ-08, expiry day, strategy 4, i41-d14-tiles-expiry-day.jpg): `Max profit Profit left / If held to expiry +5,104.10 +523.63 / If exited now +5,009.47 +429.00`. PASS (ADR-320 (2)).
- Re-buy of a closed contract (#725, #741): BLOCKED, needs an exit then a buy; scenario mode refuses orders.

## I-66
Tab B on Positions > Current positions; tab A renames the trade in the builder to `Renamed in A`. Tab B without reload: after 5 s the card reads `Renamed in A (#1, 9 Nov)`, tag `PAPER`, status `Running`, `4 of 4 positions`, figures unchanged; same at 20 s and 40 s and after a reload. The old name did not stay. A tag or status change (Running to Closed, an adjustment) needs an order, refused in scenario mode: BLOCKED. The name was put back to `Scenario ADJ-02` afterwards.

## I-71 FAIL
In the picker (Add/Edit) on the Straddles tab, "Pick from Option Chain" clicked: the tab stays `Straddles`, no Strikes panel appears (i71-03, i71-04). On the Strikes tab the link only sets the column view to LTP. Source: `frontend/src/components/strategy/LegPicker.vue:994` `@click="view = 'ltp'"`; the same file has `showStrikes()` (line 668, `selectTab('strikes')`), documented as what this link should do ("W-195 review 7").

## I-72 PASS
All 19 dropdown items of the six sections (Home 1, Strategies 6, Positions 3, Market 3, Alerts 3, Learn 3) clicked in Playwright; each lands on its own path with its own heading, including `Create Strategy` (the wizard) and `Adjustments`; no page error. Screenshots: i72-create-strategy, i72-strategy-builder, i72-adjustments. The Positions pages show `Connect your Zerodha account to continue.` (no broker here, expected).

## I-78 PASS (with a note)
More menu > Rename opens `Update Strategy Name`, field `Strategy Name`, line `That is the 20-character limit: nothing more can be typed.` Typed text then Esc: the dialog closes, the name stays `Scenario ADJ-02`, no PATCH was sent (no non-GET call logged), no toast, no status line. A dismissed rename reads as nothing (silent), which matches a cancel. vitest `rename-paper-d65.test.js`: 6 passed.

## I-79 PASS
Greeks tab on the ADJ-02 trade: `Instrument Delta Theta Decay Gamma Vega IV`, row `B 2 x 9 Nov 22500 PE -0.0067 -1.15 -0.85 0.000049 0.41 17.73%` and so on, `Total -0.21 6.87 49.04 -0.0005 -3.31`; no red error or alert on the panel; no page error.

## I-86
Each page opened in its own tab with the API stopped (start of the text):
- My Strategies and Completed Strategies: `Could not load your strategies. Nothing was changed. Retry` (Retry button).
- Live Strategies, Alerts Active, Alerts History, Positions, Adjustment opportunities, Home: the shared block `The page could not get an answer from the server. What this means: ... What to do next: Try again in a moment.` (no Retry button).
- Adjustments: `Something went wrong. Please try again.` (other wording, no Retry).
- Option Chain: `The expiries could not be read, so no chain is shown.`
After the API was started: Retry worked on My Strategies and Completed Strategies (list back within 3.5 s). Alerts Active and Home recovered by themselves. Live Strategies, Alerts History, Positions (error blocks; the paper P&L did come back), Adjustment opportunities, Adjustments and Option Chain still showed their failure text 5.5 s after the API was back and have no Retry button. I did not wait longer or reload, so "never recovers" is not claimed.

## I-88
- ADR-330 (30): the builder button reads `View`, popover `Show legs as Lots Quantity`; the avatar menu lists `Account & Settings` with `Settings` (i88-01, i88-02). The leg picker still has its own `Settings` button; the ADR names only the builder's own button, so this is an observation (O-5).
- D-52: the no-draft builder reads `Pick strikes, or start from a ready-made shape in the Ready-made tab.` and the Ready-made tab exists; the page without that tab (API down) says `...on the Create Strategy page`. PASS.
- D-54: the playbook editor shows tabs 1 to 7 (`7 Test on my strategies`), no "Test this playbook" button on the system playbook; buttons `Save as new playbook`, `Edit system playbook`, `Approve`. Delete confirmation: BLOCKED (a system playbook has no Delete; creating an own playbook is a write I did not make).
- D-58: Stops form Above = 0 reads `A price of 0 cannot be used. Enter 0.05 or more`, same for a leg stop; the old "steps of 0.05" text is gone. Names with literal quotes: none in this data, BLOCKED. `Your playbook sets no time exit` and the raw key `day.beforeHoliday.1500.0` need the adjustment drawer or opportunities on live data: BLOCKED.

## I-93 PASS
Positions > Current positions > Stops at 1280x800: form box x=92 y=802 w=536, list box x=652 y=802 w=536, same top: side by side. Saved: list `Conditional exit Above 24,000.00 armed Cancel`, status `Saved: exit above 24000`. Page scroll before Save 1005, after Save 1005 (no jump); the panel stays at the same screen position (i93-01, i93-02). O-6: the status says `24000` while the list says `24,000.00`.
This walk left one armed stop (Above 24,000) on strategy 1 and one (Above 23,900) on strategy 3 in the local ofo_dev.

## Defects found (for a fix lane)
- D-TD-1 (I-71): the footer link "Pick from Option Chain" does not open the chain from Straddles, Strangles or Futures. `frontend/src/components/strategy/LegPicker.vue:994`; it should call `showStrikes()`. Failing check: `tests_browser/r2_1128_d/i78_i71.js` (prints `tab selected after link: Straddles | strikes-panel present: 0`).
- D-TD-2 (I-86): six list pages give no Retry and use three different failure wordings. Check: `i86_lists.js`.
- D-TD-3 (set-up note, not a product defect): `seed_scenario.py` needs live catalogue rows, and the catalogue routes judge currency on the database clock, so a scenario day in the past shows "paper position could not be read" in the builder unless the API runs with APP_ENV=test and TEST_CATALOGUE_DATE=<scenario day>. One line in the scenario runbook would save the next lane an hour.

## For the owner lane
- Only D-TD-1 and D-TD-2 need code; nothing else.

## Decided for the owner
- API run with APP_ENV=test and the catalogue date pin (scenario mode allows `test`); the brief said development. Reason in Set-up.
- Extra scenarios ADJ-02a (null ltp), ADJ-13 (booked P&L) and ADJ-08 (expiry day) seeded as strategies 2, 3, 4 in the local ofo_dev; the ADJ-02a fixture is git-excluded and made by `make_null_ltp.py`.
- Contracts of ADJ-02, ADJ-13 and ADJ-08 loaded in one `load_cat.py` call because the loader refuses a list that drops more than 10 percent of live contracts (ADR-058).

## Push gate
`python tools/ci_local.py`: 14 passed, 2 failed (`git merge-base origin/main HEAD` failed, shallow clone; fixed afterwards with `git fetch origin main --unshallow`). `python scripts/orchestrator/prepush.py`: frontend_lint, frontend_build, ci_checks, frontend_unit, coverage, alembic_guard PASS; ruff_ratchet FAIL (ruff not installed; installed afterwards); domain_tests FAIL 2 of 10,700 (`tests/test_egress_gate.py::test_r4_percent_encoded_host_from_a_non_door_module` and `::test_r5_bare_urllib_then_request_urlopen`, both URLError: they open real network from this sandbox); preflight-scans FAIL on the ruff ratchet. No marker was written, so the pre-push hook blocks `git push`. A `PREPUSH_GATE_ALLOW` bypass was refused and I did not go around it.
