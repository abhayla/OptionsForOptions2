# Lane T: screen-by-screen browser tests (26 Nov 2026)

Branch `test/screen-suite-1126` from `feat/nb-screens-w2-1126` a9bd41a. Tests, helpers and docs only; no product
code, no spec rows, no migration. Owner evidence: comment 7184365037 on PR #722 (26 Nov screen test).

## Status

| Screen | Spec file | Tests (x2 viewports) | Expected-fail (ids) | New findings | Pushed head |
|---|---|---|---|---|---|
| Core proof (Home row 2 > builder) | `frontend/e2e/screen-home.spec.ts` | 1 | 0 | 0 | 57508da |
| Home | `frontend/e2e/screen-home.spec.ts` | 79 | 5 (N-18 x2, NEW-T01, NEW-T02, NEW-T03) | 3 | (this commit) |

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

Screenshots are written by the tests to `frontend/test-results/lane-t/` (gitignored; regenerated on each run).

## Not covered yet (Home)

- Welcome / trial slot: nothing to click until sign-in exists; only the absent text is asserted (NEW-T01).
- Header toast for a new adjustment opportunity: needs a second header poll; the record count is covered (BELL-4).
- R-06 same-moment sum of the My Strategies rows: not provable against stubs; Home vs Positions headline is covered.
- Hover-open menus (150 ms delay) and arrow-key menu navigation; click, Escape and outside click are covered.
