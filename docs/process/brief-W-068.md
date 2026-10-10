# Builder brief: W-068 - leg picker (REQ-035 AC-8)

Core: Zerodha's real public instrument list, applied to the real catalogue store with apply_update, answers the
picker query with listed, not-expired contracts of one underlying grouped by expiry and strike.
Proof: ALREADY PROVEN by the orchestrator on 2026-10-10 (see `work/W-068.md` frontmatter `proof`: 4,948 contracts
loaded in 2.5 s, NIFTY 13-Oct-2026 108 CE + 108 PE, rolled back). Your step 1 repeats it through YOUR new store
function as a network-marked, rolled-back test before you build the route or the UI.

Tier: B. Model: sonnet/medium. Budget: 90 min wall-clock, 110 tool calls. Commit after each step; at budget stop
after a commit and report done / not done / next command. Report: evidence-table
(`| Claim | Evidence (command run this turn) |`), under ~300 words.
Worktree: `C:\Abhay\Ventures\OptionsForOptions2-W-068`, branch `build/W-068-leg-picker` (already created; work only
there; commit there; do NOT push - the orchestrator pushes).
Copy from: legacy-reuse rows `src/views/StrategyBuilderView.vue` (2094), `stores/strategy.js` (969) - ADAPT (P4):
the leg add/edit form shape only; drop client P&L (`stores/strategy.js:722-743`), price fallbacks (`:359-374`) and the
basket call (`:622`). Expiries, strikes and lot sizes come only from our catalogue (legacy-reuse row 10). Read
algochanakya at commit `bf9faf7` only for those two files; nothing else.

## LOAD CAP - this PC's PostgreSQL serves IPODhan PRODUCTION
- Targeted test files only, one at a time, through `scripts/orchestrator/db_run.py` (set `OFO_GLOBAL_ENV=C:\Abhay\GLOBAL.env`).
  Every DB probe under 30 s. Never the full app suite, never Playwright, never `npm run build` here - CI runs those.
- `ofo_test`'s catalogue MUST stay empty after every test (other tests assert it): every DB test rolls back.

## Spec basis (quoted verbatim)
- REQ-035 AC-8: "The Builder adds and edits legs from a picker that offers only listed, not-expired contracts of the
  chosen underlying (underlying, expiry, strike, CE/PE/FUT, buy/sell, lots) (ADR-068 item 4; owner 2026-10-10)."
- ADR-068 (1): "A draft leg's entry price is its planned entry: the leg's LTP captured when the leg is added (or the
  mid of bid and ask when no LTP exists)". ADR-068 (4): "offers only listed, not-expired contracts; Zerodha's own
  eligibility check comes with orders in 4b."
- ADR-020 Q186: "without Zerodha — choose underlying/strategy, edit legs, set rules, save ✅; live prices, Greeks,
  P&L, live margin, executable orders ❌". Q185: drafts marked "Draft — Live data not connected"; "no fake prices".
- ADR-008: one engine owns every P&L number; the browser computes none. ADR-012: the browser never talks to Zerodha.
- ADR-003 Q226: every user-facing message comes from the template catalogue; reuse `gate_underlying_unsupported`
  (USER_INPUT_101) for an unsupported underlying. A NEW message needs a NEW template in
  `backend/ofo/errors/templates.py` + its pin in `tests/errors/template_pins.json` as "pending owner read".

## Do (in order)
1. **Store function + real-data test (core, first).** In `backend/ofo_app/` add a read-only catalogue query:
   `pickable_contracts(conn, underlying, today, expiry=None)` -> live (`NOT retired AND NOT delisted`), `currently
   listed`, `expiry >= today` contracts of that underlying with instrument_id (`"<exchange_segment>:<exchange_token>"`,
   the id the outcome route takes), instrument_type, expiry, strike (Decimal, None for FUT), lot size and Zerodha
   symbol; plus `pickable_expiries(conn, underlying, today)`. `today` is a parameter (the route passes the DATABASE
   clock's date in Asia/Kolkata: `(now() AT TIME ZONE 'Asia/Kolkata')::date`); never `date.today()`.
   Tests `tests_app/test_catalogue_picker_api.py`: (a) deterministic - load `tests/fixtures/instruments/instruments_slice.csv`
   with `apply_update(..., as_of=<2026-09-28 timestamp>)` inside a rolled-back transaction, query with
   `today=2026-10-07`: 2026-10-08 rows present, 2026-10-06 and 2026-10-01 rows absent, a delisted and a retired row
   absent, only the asked underlying; (b) `@pytest.mark.network` - the real list, rolled back, today = DB clock date:
   NIFTY returns at least one expiry with both CE and PE strikes.
2. **API (read-only).** `GET /api/catalogue/{underlying}/expiries` and `GET /api/catalogue/{underlying}/contracts?expiry=YYYY-MM-DD`
   following the route, model and error patterns of `backend/ofo_app/routes/strategies.py` (closed ApiModel response
   models, money/strike as strings, the four-part error body). Underlying not NIFTY/SENSEX -> USER_INPUT_101. An expiry
   that is past or unknown -> empty list (not an error). Route tests in the same test file (as the limited `ofo_app` role).
3. **Planned-entry capture.** `POST /api/strategies/planned-entry` {underlying, instrument_ids} -> per id either
   `{planned_entry: "<price>", captured_at, source: "ltp"|"mid"}` or `{planned_entry: null, reason_code}` when no live
   price. Read prices ONLY through `ofo.outcome.read_snapshot` with the same provider dependency the outcome route uses
   (`backend/ofo_app/routes/outcome.py`), so replay (`APP_ENV=test` + `OUTCOME_REPLAY=1`) works in tests. LTP first;
   mid of bid and ask only when no LTP; nothing when the provider is not live or the quote is missing - NEVER a
   default, last-known or zero price. Test with the recorded `tests/fixtures/kite_ws/` replay: one leg gets its LTP,
   one id with no quote gets null.
4. **Load command.** `python -m ofo_app.catalogue_load` (or a function it calls): download the public list, parse with
   `parse_rows_naming_the_row`, `apply_update(conn, rows, as_of=<DB clock_timestamp()>)`, commit, print the
   StoreUpdateResult counts; a guard refusal prints the refusal and exits non-zero with nothing written. Test
   `tests_app/test_catalogue_load_command.py` with the fixture slice (rolled back) + the refusal path. No scheduler.
5. **Frontend.** A `LegPicker` component on `StrategyBuilderPage.vue`: underlying (NIFTY/SENSEX) -> expiry (from the
   API) -> CE/PE/FUT -> strike (from the API; none for FUT) -> BUY/SELL -> lots (whole number 1-10000) -> Add. Each
   leg row has Edit (change any field, re-picked from the API) and Remove. The page's draft is built from the picked
   legs and sent to the outcome API as today; a leg without a planned entry is shown with "Draft — Live data not
   connected" wording from the existing not-connected state (do not invent new copy; if you need new text, add a
   template as above). The existing `?draft=` query path keeps working. The browser parses no price to compute
   anything. Vitest `frontend/tests/leg-picker.test.js` (mocked API: only offered contracts are selectable, FUT has no
   strike, lots validation, edit/remove). Playwright `frontend/e2e/leg-picker.spec.ts` (runs in CI only; seed the
   catalogue the way the CI app job seeds other e2e data - read `.github/workflows/app-tests.yml` with the Read tool).

## Reviewer checklist (the reviewer will check exactly these - make each true and tested)
- Not-expired is judged on the DB clock in IST via a `today` parameter; no `date.today()`/`datetime.now()` in new code.
- Only live, currently listed, not-delisted, not-retired contracts of the asked underlying are returned (test proves
  each exclusion with a real fixture row).
- No price is ever invented: capture returns null without a live quote; the browser never computes a price.
- New routes use closed response models and catalogue messages; no free text reaches a user.
- Every DB test rolls back; `SELECT count(*) FROM public.catalogue_contracts` is 0 after your test file runs.
- `tests/` never imports `ofo_app` (guard `tests/test_no_app_imports.py`); every `tests_required` file exists.

## Checks before you report (each as its own plain command, from the worktree root)
- `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_catalogue_picker_api.py`
  (and the load-command file; add `-m "not network"` first, then run the network tests once)
- `python -m pytest -q -p no:cacheprovider tests/test_spec_integrity.py tests/test_no_app_imports.py tests/test_tests_required_exist.py tests/errors`
- in `frontend/`: `npm run lint`, `npx vitest run tests/leg-picker.test.js`
- grep `tests/` and `tests_app/` for every route, template code and message you touched (finding
  targeted-tests-miss-dependent-files) and run the hits.
Never pipe a check into `tail`/`head` before a commit (the project hook refuses it); send long output to a log file.
