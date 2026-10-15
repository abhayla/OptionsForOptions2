# Builder brief: W-071 round 2 - Save Draft and reopen, with the two API bridge fields (Tier B)

Core: a draft built in the real Builder screen, saved through its Save Draft action against the real API, reopens
from the saved list with identical legs, planned entries and capture times.
Proof: step 1 is `frontend/e2e/strategy-save-draft.spec.ts` against the running API with REAL catalogue rows in the
test database (seeded from the recorded fixture, removed afterwards), written first and red, then green.

Tier: B. Model: sonnet.
Budget: 30 min wall-clock, 60 tool calls - a hard limit: count your calls; at 55 commit, push and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: legacy-reuse row 146 (`StrategyBuilderView.vue`, `stores/strategy.js`, ADAPT: save/load calls only; no
client P&L, no price fallbacks, no basket call).

## Why round 2
Round 1 stopped correctly at the core (no code): POST /strategies takes each leg's internal `contract_id`, but no route
the browser reads returns it; and a saved leg (`LegOut`) returns `contract_id` and symbol but not the segment and token
the outcome API prices by. Decided from the spec (work/W-071.md "Card correction"), not an owner question:
- ADR-057: "A strategy leg, an order and an audit record link to the stored contract (its internal id), never to the raw token"

## Spec basis
- REQ-038 AC-5: "A strategy's definition and its activity history are saved in the database when the user presses
  Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the strategy."
- REQ-038 AC-5: "Each leg's planned entry price and its capture time are part of the definition and are saved with it"
- ADR-068 (1): "it changes only when the user asks to reprice, never with the live price"
- ADR-068 consequence: "the screen does no P&L maths (ADR-008)"

## Start
Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-071`, branch `build/W-071-save-draft` (main ad3cbd4 + the corrected
`work/W-071.md`, uncommitted: commit it first). `npm ci` is done. Read: `backend/ofo_app/routes/catalogue.py`
(`ContractOut`), `routes/strategies.py` (`LegIn`, `LegOut`, how a leg is loaded), `catalogue_load.py` (the load command),
`tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv`, `frontend/src/pages/StrategyBuilderPage.vue`,
`frontend/src/components/LegPicker.vue` (or wherever the picker lives), `frontend/e2e/leg-picker.spec.ts`,
`frontend/e2e/support/quiet-live.ts`, `.github/workflows/app-tests.yml` (frontend job order).

## What to build
1. **Backend (additive only):** `ContractOut` gains `contract_id` (int, the catalogue's internal id); `LegOut` gains
   `exchange_segment` and `exchange_token` of the leg's stored contract. Regenerate the committed OpenAPI file(s)
   (`scripts/generate_openapi.py`; the drift test). App tests for both fields in the existing route test files.
2. **e2e data:** the save-draft spec's setup loads catalogue rows for the recorded fixture
   (`instruments-2026-10-08-subscribed.csv`) into the test database through the existing load path (or a test-only
   helper that calls it), and its teardown removes exactly what it added plus the drafts it saved, so `ofo_test` is
   empty again (finding live-work-shares-test-database: leftover rows break other tests). Never load live data. If the
   ADR-058 delist guard or the `ofo_app` role's grants refuse this, STOP and report rather than loosening either. Wire
   the same setup into CI's frontend job if it needs a step there.
3. **Screen:** the picker carries `contract_id` on each leg; Save Draft POSTs legs with `contract_id`, action,
   `quantity` = lots x lot size, planned entry and capture time (ADR-075). A saved-drafts list (GET /strategies) and
   reopen (GET /strategies/{id}) rebuild the legs from `LegOut` (segment:token for the outcome API, planned entry and
   capture time exactly as stored, never re-captured). A pre-ADR-075 draft (no entries) reopens with entries missing
   and asks for a reprice. Messages from the catalogue only (W-024 rules).
4. Unit tests `frontend/tests/save-draft.test.js`.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutations: re-capture the entry on reopen; drop `captured_at` or `planned_entry` from the POST body; put a live LTP
  in the body; send `instrument_id` instead of `contract_id`; show a raw error string; compute P&L in the browser.
- Assert the exact POST body keys per leg; reopen compares every leg field (underlying, expiry, strike, CE/PE,
  buy/sell, lots, planned entry, capture time) with what was saved.
- Fail closed: an answer the page cannot parse shows the catalogue error and keeps the unsaved draft on screen. List
  every answer state (201, 4xx catalogue error, 5xx, network down, empty list, 404 on reopen) and what each shows.
- The e2e teardown leaves `ofo_test`'s catalogue and strategy tables as it found them: assert the counts.

## Rules
- `ofo_test` is on a production host (tunnel 127.0.0.1:5432): targeted test files only, never the full app suite.
  DB commands from `D:\Abhay\Ventures\OptionsForOptions2` through
  `python scripts/orchestrator/db_run.py D:\Abhay\Ventures\OptionsForOptions2-W-071 <command>`.
- Frontend: `npm run lint`, `npx vitest run`, `npm run build`; Playwright only the new spec and `leg-picker.spec.ts`,
  servers started as app-tests.yml does (placeholder `KITE_*`/`BROKER_TOKEN_KEY` from lines 80-84;
  `PW_CHROMIUM_PATH` for the local Chromium if the pinned one is missing). Stop every server by PID.
- No migration, kit, `spec/` or `evidence/` change; never mark anything verified. Commit and push
  `build/W-071-save-draft`; no PR.
