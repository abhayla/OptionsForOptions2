# Builder brief: W-071 Save Draft and reopen in the Strategy Builder screen (Tier B)

Core: a draft built in the real Builder screen, saved through its Save Draft action against the real API, reopens
from the saved list with identical legs, planned entries and capture times.
Proof: step 1 is a Playwright spec against the running API (as the frontend CI job runs it): build a 4-leg draft,
press Save Draft, reload the page, reopen the draft from the list, compare every leg field and planned entry with what
was saved. Write that spec FIRST and make it red, then build until it is green.

Tier: B. Model: sonnet.
Budget: 30 min wall-clock, 60 tool calls. Commit after each step; at budget stop after a commit and report done /
not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: legacy-reuse row 146 (`src/views/StrategyBuilderView.vue`, `stores/strategy.js`, ADAPT): the save/load
calls only; delete client P&L (`stores/strategy.js:722-743`), price fallbacks (`:359-374`) and the basket call
(`:622`) - none of those come across.

## Spec basis
- REQ-038 AC-5: "A strategy's definition and its activity history are saved in the database when the user presses
  Save Draft, survive a restart, and load back exactly as saved; live prices are never saved inside the strategy."
- REQ-038 AC-5: "Each leg's planned entry price and its capture time are part of the definition and are saved with it"
- ADR-068 (1): "it changes only when the user asks to reprice, never with the live price"
- ADR-008 / ADR-068 consequence: "the screen does no P&L maths (ADR-008)"

## Start
- Branch `build/W-071-save-draft` from current main (W-065 phase 3 is merged: the page now has the live socket; do
  not change `useStrategyLive.js` behaviour).
- Read: `frontend/src/pages/StrategyBuilderPage.vue`, its stores/composables, `frontend/src/api/` (or wherever the
  fetch helper lives), `backend/ofo_app/routes/strategies.py` (POST /strategies, GET /strategies,
  GET /strategies/{id}: request/response shapes; NO backend change in this item), `frontend/e2e/strategy-*.spec.ts`
  and `frontend/e2e/support/quiet-live.ts` (how REST-path specs keep the live socket silent).

## What to build
1. `frontend/e2e/strategy-save-draft.spec.ts` (the core proof, red first), at 1280 and 390.
2. A Save Draft action on the Builder page: POST /strategies with the legs exactly as the page holds them, including
   each leg's planned entry and capture time (ADR-075). Success and failure states use the existing message catalogue
   (W-024 rules: no free text; a failure shows the catalogue's message, never a raw error).
3. A saved-drafts list (GET /strategies) and reopen (GET /strategies/{id}) that restores the legs and planned entries
   exactly; reopening NEVER re-captures an entry. A draft saved before ADR-075 (no entries) reopens with entries
   missing and asks for a reprice (no entry is invented).
4. Unit tests `frontend/tests/save-draft.test.js`.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutations: re-capture the entry on reopen; drop capture time from the POST body; save a live LTP into the strategy;
  show a raw error string; compute any P&L in the browser.
- The saved payload holds no live price field (assert the exact POST body keys).
- Reopen compares every leg field (underlying, expiry, strike, CE/PE, buy/sell, lots, planned entry, capture time).
- Standing items: fail closed on an API answer the page cannot parse (show the catalogue error, keep the unsaved
  draft on screen); list every API answer state (201, 4xx catalogue error, 5xx, network down, empty list) and what
  each shows.

## Rules
- The test database is ofo_test on a production host (tunnel 127.0.0.1:5432): targeted files only, never the full
  app suite. Frontend: `npm run lint`, `npm run test:run`, `npm run build`; Playwright only your new spec plus the
  `strategy-*` specs, against servers you start as `.github/workflows/app-tests.yml` does (API on 8000 through
  `scripts/orchestrator/db_run.py`, `vite preview` on 4173). Stop every server you start, by PID.
- No backend, migration, kit or `spec/` change. Never write `evidence/`. Never mark anything verified.
- Commit and push `build/W-071-save-draft`. Do not open a PR.
