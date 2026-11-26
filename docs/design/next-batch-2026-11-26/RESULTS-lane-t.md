# Lane T: screen-by-screen browser tests (26 Nov 2026)

Branch `test/screen-suite-1126` from `feat/nb-screens-w2-1126` a9bd41a. Tests, helpers and docs only; no product
code, no spec rows, no migration. Owner evidence: comment 7184365037 on PR #722 (26 Nov screen test).

## Status

| Screen | Spec file | Tests (x2 viewports) | Expected-fail (ids) | New findings | Pushed head |
|---|---|---|---|---|---|
| Core proof (Home row 2 > builder) | `frontend/e2e/screen-home.spec.ts` | 1 | 0 | 0 | 57508da |
| Home | `frontend/e2e/screen-home.spec.ts` | 79 | 5 (N-18 x2, NEW-T01, NEW-T02, NEW-T03) | 3 | 7c90919 |
| Coverage guard | `frontend/tests/screen-inventory-guard.test.js` (vitest, runs in `npm run test:run`) | 1 | 0 | 0 | 2796b56 |
| My Strategies | `frontend/e2e/screen-my-strategies.spec.ts` | 100 (LIST-9 mobile only) | 2 (NEW-T10, NEW-T11) | 2 | a6ed1c6 |
| Current positions | `frontend/e2e/screen-positions.spec.ts` | 142 (stable: 568 passed with `--repeat-each 2`) | 6 (NEW-T20, NEW-T21/N-05, NEW-T22/N-04, NEW-T23, NEW-T24, N-01) | 5 | 4d9cbaa |

Core proof: the row-2 test failed under one mutation (`HomeOverviewPage.vue` row link pinned to row 1: "Expected
/strategy\/builder\?strategy=7$/ Received .../strategy/builder?strategy=12") and passed again after the revert.

How the suite runs: built app on `vite preview` (port 4175, `OFO_API_TARGET=http://127.0.0.1:9`) with `page.route`
stubs, the way the existing `home.spec.ts` runs; `PW_CHROMIUM_PATH=/opt/pw-browsers/chromium-1243/chrome-linux64/chrome
npx playwright test e2e/screen-home.spec.ts --trace off` from `frontend/`. The real-backend mode CI uses (Postgres 16,
migrated, 2026-10-08 catalogue seeded, uvicorn 8000-8002, previews 4173-4176) also works in this container.

## Findings (product defects; steps, spec, actual)

| Id | Screen | Steps | Expected (spec) | Actual | Test | Screenshot |
|---|---|---|---|---|---|---|
| N-18 (owner R-06) | Home | Open Home with paper totals `+13,410.44` after charges; read the Total P&L tile name | "Total P&L (after charges)" (REQ-109 AC-10, ADR-320 (6)) | "(after charges) (after charges)", no name; same with "(before charges)" | `R-06 / N-18`, `FIG-2` | `frontend/test-results/lane-t/N-18-1280.png`, `N-18-before-1280.png` |
| NEW-T01 | Home | Open Home with no strategies | "Welcome, [Name]" and the 7-day Pro trial status with end date (REQ-008 AC-3) | Neither line; the code defers it to sign-in (row #433, Stage 5) | `STATE-3` | `NEW-T01-1280.png` |
| NEW-T02 | Home | Paper list answers `prices_not_live` with `totals_as_of` 10:00 IST | "Paper P&L paused - prices not live, as of 26 Nov 2026, 10:00:00 IST" (REQ-109 AC-5) | Sentence without the as-of time | `STALE-2` | `NEW-T02-1280.png` |
| NEW-T03 | Home | Paper list answers 500 or paused | Tile keeps the name "Total P&L" with "—" | Name is empty: `pnlFigure` returns `label: ''` and overrides it (same code path as N-18) | `STALE-3` | `NEW-T03-1280.png` |

| NEW-T10 | My Strategies | Rename on any row, type, press Escape | Esc cancels the rename (inventory MYSTR-11; owner R-05 left Escape unverified). Spec text is silent on Escape: question for the coordinator | The rename box stays open | `RENAME-5` | `NEW-T10-1280.png` |
| NEW-T11 | My Strategies | `GET /strategies` answers 200 with an unreadable body (proxy HTML page) | Fail closed: "Could not load your strategies. Nothing was changed." with Retry (ADR-330 S-05, REQ-065) | Read as an empty list: shows "You have no saved strategies yet..." and no Retry | `LOAD-4` | `NEW-T11-1280.png` |

| NEW-T20 | Current positions | `GET /positions` answers 200 `{unexpected:true}`; open Current positions | Unreadable answer shows the failure message, never an empty or blank section (REQ-044 AC-3, ADR-008) | Real section shows no failure message | `REAL-14` | `NEW-T20-1280.png` |
| NEW-T21 (owner N-05) | Current positions | Paper P&L > Exit after a failed re-read (Exit disabled) | A blocked action looks disabled (owner N-05, ADR-328 (4)) | Disabled and enabled Exit have identical computed opacity, colour, background, border | `EXIT-20` | `NEW-T21-1280.png` |
| NEW-T22 (owner N-04) | Current positions | Tick a leg, open Exit, let the re-read fail (dialog closes itself), let prices return | Nothing staged is left when the page closes the dialog (owner N-04) | Tick stays; "Exit (1)" enabled again | `EXIT-21` | `NEW-T22-1280.png` |
| NEW-T23 | Current positions | First `GET /paper/strategies` answers 500 | Paper total shows the same paused reason as the list (ADR-330 (10)) | Dash with no reason line | `TOT-11` | `NEW-T23-1280.png` |
| NEW-T24 | Current positions | `GET /positions` 500, then `GET /broker/status` answers non-JSON | Unreadable status is a failed read, not "not connected" (REQ-015 AC-10; PositionsPage's own rule); AC-10 is ambiguous: question | `data-state=not_connected` | `REAL-13` | `NEW-T24-1280.png` |
| N-01 (owner) | Current positions | Stops: save a refused level, wait for the next good list re-read | The "Not saved:" refusal line stays (owner N-01) | Cleared by the next re-read | `STOP-11` | - |

Screenshots are written by the tests to `frontend/test-results/lane-t/` (gitignored; regenerated on each run).

## Coverage guard

`screen-inventory-guard.test.js` rebuilds the inventory from the router and the `.vue` templates and fails, naming
file:line and label, when a route or control has no row in `screen-inventory.json`, or a row's control is gone.
Matching is on source file + kind + testid-or-label, not the positional id. Proof: a temporary `<button>Lane T probe</button>`
in `HomeOverviewPage.vue` made it fail with `HomeOverviewPage.vue:81 button "Lane T probe"`; reverted.

## Not covered yet (Current positions)

- Live index line in the Stops panel (needs the WebSocket feed); only "Index values unavailable." is tested.
- Real exit dialog: none on this screen (ADR-281); its absence is tested.
- Held-at-my-broker form, Add-to-Paper dialog, Greeks panel with data: not reachable from Positions or not exercised.
- Real-backend round trip (all stubbed).

## Not covered yet (My Strategies)

- Real-API round trip stays in `my-strategies.spec.ts` (needs the live catalogue); this suite is stubbed.
- After-charges tap on a Completed row's net figure (SHARED-09); Builder's Saved-list delete (Builder screen).

## Not covered yet (Home)

- Welcome / trial slot: nothing to click until sign-in exists; only the absent text is asserted (NEW-T01).
- Header toast for a new adjustment opportunity: needs a second header poll; the record count is covered (BELL-4).
- R-06 same-moment sum of the My Strategies rows: not provable against stubs; Home vs Positions headline is covered.
- Hover-open menus (150 ms delay) and arrow-key menu navigation; click, Escape and outside click are covered.
