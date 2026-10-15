---
work_item: W-071
ac: AC-5
requirement: REQ-038
ac_fp: "9b49fc3acd93"
result: pass
verified_by: "verifier (Sonnet, round 3 + round-4 re-check)"
builder: "builder (Sonnet, rounds 1-5)"
date: '2026-10-15'
commands: "python tools/ac_fp.py REQ-038 AC-5 -> 9b49fc3acd93 (orchestrator); db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_openapi_drift.py -> 1 passed; npx vitest run (frontend) -> 8 files, 99 passed; API through scripts/orchestrator/dev_run.py on ofo_dev (today's real catalogue, 7,397 rows) port 8000, npm run build, vite preview 4173, E2E_DEV_CATALOGUE=1 npx playwright test e2e/strategy-save-draft.spec.ts -> passed at 390 and 1280; without the flag -> 2 skipped (reason: needs a current real catalogue, #237). Round 3 (6bf7092, Sonnet verifier): pytest test_catalogue_picker_api + test_strategy_store -> 113 passed, 1 failed (stale openapi.json, fixed in a0e9f24)."
---

AC: AC-5
result: pass
commands: python tools/ac_fp.py REQ-038 AC-5 -> 9b49fc3acd93 (orchestrator); db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_openapi_drift.py -> 1 passed; npx vitest run (frontend) -> 8 files, 99 passed; API through scripts/orchestrator/dev_run.py on ofo_dev (today's real catalogue, 7,397 rows) port 8000, npm run build, vite preview 4173, E2E_DEV_CATALOGUE=1 npx playwright test e2e/strategy-save-draft.spec.ts -> passed at 390 and 1280; without the flag -> 2 skipped (reason: needs a current real catalogue, #237). Round 3 (6bf7092, Sonnet verifier): pytest test_catalogue_picker_api + test_strategy_store -> 113 passed, 1 failed (stale openapi.json, fixed in a0e9f24).
observed: A 4-leg draft built in the Builder, saved through Save Draft (POST /strategies with contract_id, action, quantity = lots x lot size, planned_entry, captured_at), reopened from the saved list (GET /strategies, GET /strategies/{id}) with every leg field, planned entry and capture time identical; the planned-entry capture route is aborted and counted on reopen and must be 0 (it was 0). Planned-entry capture at build time is stubbed in the e2e (no live ticks on ofo_dev); catalogue, POST, list and GET are real. A draft saved without planned entries reopens with the owner-approved reprice prompt and captures nothing until the user presses Reprice (unit test; the API cannot create a pre-ADR-075 draft for the e2e). The browser save flow never runs in CI (#237).
attack: Re-capture on reopen: aborted and counted, 0. POST body keys asserted exactly; no ltp, no instrument_id. Stale API contract: round 3 FAILED on the OpenAPI drift test, fixed and re-verified. Reprice: 0 POSTs on mount, one only after Reprice then Save leg. Not covered: the 4 leg-picker.spec.ts replay-server (port 4175) cases were not run locally (CI runs them); a reopened leg whose expiry left the catalogue cannot be repriced (LOW).

Recorded by the orchestrator from the verifier's returned block.
