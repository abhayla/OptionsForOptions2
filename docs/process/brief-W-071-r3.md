# Builder brief: W-071 round 3 - Save Draft and reopen; core proof on ofo_dev's real catalogue (Tier B)

Core: a draft built in the real Builder screen, saved through its Save Draft action against the real API, reopens
from the saved list with identical legs, planned entries and capture times.
Proof: step 1 is `frontend/e2e/strategy-save-draft.spec.ts` against the real API running on `ofo_dev`, which holds
today's REAL public instrument list (loaded 2026-10-15 by the orchestrator: 7,397 rows, 7,395 pickable; next expiries
2026-10-19, 2026-10-22, 2026-10-27 - pick 2026-10-19 or later, never today's 2026-10-15). Red first, then green.

Tier: B. Model: sonnet.
Budget: 30 min wall-clock, 60 tool calls - a hard limit: count your calls; at 55 commit, push and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: legacy-reuse row 146 (ADAPT: save/load calls only; no client P&L, no price fallbacks, no basket call).

## Changes from round 2 (`docs/process/brief-W-071-r2.md` - everything else there still applies)
Round 2 stopped correctly: seeded rows cannot be removed from `ofo_test` (no DELETE grant; owner role refused by the
guard triggers), and recorded fixtures age past expiry, which the save route refuses. Decided (issue #237):
1. **Replace round 2's step 2 (e2e data).** Do NOT seed `ofo_test`. The save-draft spec runs only when
   `E2E_DEV_CATALOGUE=1` is set; otherwise it is SKIPPED with the visible reason "needs a current real catalogue
   (#237)". Drafts it saves stay in `ofo_dev` (the development database, ADR-078); give them an identifiable
   `rules_ref` or preference value so a person can see they came from the e2e.
2. Run the API for the proof with `DATABASE_URL = DEV_DATABASE_URL`, through the orchestrator's wrapper (prints no
   secret, refuses anything but ofo_dev), from `D:\Abhay\Ventures\OptionsForOptions2`:
   `python C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\4b112add-c2b9-4a08-b5d6-b3bbac8c47e6\scratchpad\dev_run.py D:\Abhay\Ventures\OptionsForOptions2-W-071 python -m uvicorn --factory ofo_app.main:create_app --app-dir backend --host 127.0.0.1 --port 8000`
   (no `LIVE_MARKET`, no `OUTCOME_REPLAY`; if the app needs other settings, read them from `config.py` and say which).
   Then `npm run build`, `OFO_API_TARGET=http://127.0.0.1:8000 npx vite preview --port 4173 --strictPort`, and
   `E2E_DEV_CATALOGUE=1 npx playwright test e2e/strategy-save-draft.spec.ts e2e/leg-picker.spec.ts`. Stop servers by PID.
3. CI coverage that stays: the backend fields' route tests in `tests_app/` (rolled-back transactions on `ofo_test`,
   as the existing route tests do) and `frontend/tests/save-draft.test.js`.

## Spec basis
- ADR-057: "A strategy leg, an order and an audit record link to the stored contract (its internal id), never to the raw token"
- REQ-038 AC-5: "Each leg's planned entry price and its capture time are part of the definition and are saved with it"
- ADR-068 (1): "it changes only when the user asks to reprice, never with the live price"

## What to build (as round 2, in this order)
1. The e2e spec (red).  2. Backend additive fields: `ContractOut.contract_id`; `LegOut.exchange_segment` +
`exchange_token`; OpenAPI regenerated; route tests.  3. Screen: picker carries `contract_id`; Save Draft POST; saved
list + reopen from `LegOut`; never re-capture on reopen; pre-ADR-075 draft asks for a reprice; catalogue messages only.
4. `frontend/tests/save-draft.test.js`.  Reviewer checklist: round 2's, unchanged.

## Rules
`ofo_test`: targeted test files only, via `scripts/orchestrator/db_run.py`. `ofo_dev`: only through `dev_run.py`, only
the API process for the e2e; no truncation, no migration, no catalogue load (already done). No kit, `spec/` or
`evidence/` change. Commit and push `build/W-071-save-draft` (it already holds e54ef4b); no PR.
