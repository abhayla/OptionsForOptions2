# Builder brief: W-072 contract names, IST times, four-part errors on the Builder screen (Tier B)

Core: the real Builder page, with a leg added from the real catalogue and a priced answer from the real API, shows the
leg as `<UNDERLYING> <D Mon> <strike> <CE|PE>`, the priced-at time as `<D Mon YYYY>, <HH:MM:SS> IST`, and a catalogue
error with its four labelled parts - no `NSE_FO:` and no ISO time text anywhere on the page.
Proof: step 1 is `frontend/e2e/strategy-display-format.spec.ts` against the running API and `vite preview` (as
`.github/workflows/app-tests.yml` starts them). Write it FIRST, make it red on current main, then build until green.

Tier: B. Model: sonnet.
Budget: 30 min wall-clock, 45 tool calls. This is a HARD limit: count your calls; at call 42 commit what you have,
push, and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - the legacy-reuse map has no formatter row; the legacy footer's `toLocaleString` used the browser's
time zone, which ADR-086 forbids, and was removed on copy (see the comment in `StrategyFooter.vue`).

## Spec basis
- ADR-086: "every leg is named by its contract" and "never by an internal or broker id" (example in the ADR:
  `NIFTY 19 Oct 23200 CE`, never `NSE_FO:47171`).
- ADR-086: "every time is shown in India time" (format `15 Oct 2026, 11:59:59 IST`, whatever the browser's zone).
- ADR-086: errors "inside the leg picker and the Save Draft bar" too: all four parts, "each under its label".
- REQ-039 AC-3: "Every important non-normal state shows what happened, when, what is blocked and the next action"
- ADR-086: "no money is formatted here" - never format or compute a money value (ADR-008).

## Start
- Branch `build/W-072-display-format` from current main.
- Read: `frontend/src/pages/StrategyBuilderPage.vue`, `frontend/src/components/strategy/` (LegPicker, SaveDraftBar,
  SummaryCards, StrategyFooter, AdvancedDetails), `frontend/src/components/common/ErrorMessage.vue`,
  `frontend/src/services/api.js`, `frontend/e2e/strategy-*.spec.ts`, `frontend/e2e/support/quiet-live.ts`.

## Known sites (the class; find the rest with grep, do not stop at this list)
- Raw ids: `StrategyBuilderPage.vue:193` (`{{ leg.instrument_id }}`), `LegPicker.vue:179` (`symbol ?? instrument_id`),
  `AdvancedDetails.vue:19`, `StrategyBuilderPage.vue:207` (`{{ l.symbol }}` - a broker trading symbol is not a
  contract name either).
- ISO times: `StrategyFooter.vue:7` (`lastUpdated`), `SummaryCards.vue:58`, `LegPicker.vue:235` (`captured ...`),
  plus any saved-draft list time in `SaveDraftBar.vue`.
- Compact errors without labels and without impact: `LegPicker.vue:187`, `SaveDraftBar.vue:77`.

## What to build
1. The e2e spec (core proof), at 1280 and 390: page text has no `/[A-Z]+_FO:\d+/` and no
   `/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/`; the leg name and priced-at time match the formats; a forced leg-picker error shows
   four labelled parts.
2. ONE `frontend/src/lib/displayFormat.js` with `contractName(leg)` and `istTime(iso)`; every site above uses it.
   `contractName` builds from underlying, expiry, strike, type (strike `23200.00` -> `23200`; a non-whole strike keeps
   its decimals; FUT legs have no strike). Where a leg lacks those fields (outcome answer legs), look them up from the
   page's draft legs by `instrument_id`; if still missing, show `Contract details not available` - never the id.
   `istTime` always formats in `Asia/Kolkata`; an unparseable value shows `Time not available`, never the raw string.
3. Compact errors: render through `ErrorMessage.vue` (add a `compact` prop if needed) so all four parts and their
   labels show; delete the run-together templates. Keep the `data-testid`s other specs use, or update those specs.
4. Keep raw values in `data-*` attributes where existing specs read them; update every spec/unit test that asserted
   the raw text.
5. Unit tests `frontend/tests/display-format.test.js` and `frontend/tests/error-parts.test.js`.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutations: return the id from `contractName`; format in the browser's zone instead of Asia/Kolkata (run the unit
  test with `TZ=America/New_York`); drop the impact part in compact mode; show the raw string on a bad time.
- Exact expected strings: `contractName` of NIFTY 2026-10-19 23200.00 CE is `NIFTY 19 Oct 23200 CE`;
  `istTime` of `2026-10-15T11:59:59.362869+05:30` is `15 Oct 2026, 11:59:59 IST`; of `2026-10-15T06:29:59Z` is
  `15 Oct 2026, 11:59:59 IST`.
- A grep over `frontend/src` for `instrument_id }}` and `.captured_at }}` in templates finds nothing.
- No money value is formatted or computed in the browser (ADR-008).

## Rules
- Frontend only: no backend, migration, kit or `spec/` change. Never write `evidence/`. Never mark anything verified.
- The test database is ofo_test on a production host: no app test files are needed here; do not run `tests_app`.
  Frontend: `npm run lint`, `npm run test:run`, `npm run build`; Playwright only your new spec plus the `strategy-*`
  specs, against servers you start as `app-tests.yml` does (API on 8000 through `scripts/orchestrator/db_run.py`,
  `vite preview` on 4173). Stop every server you start, by PID. Long output to a log file, tail only.
- Commit and push `build/W-072-display-format`. Do not open a PR.
