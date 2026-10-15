# Verifier brief: W-071 Save Draft and reopen (Tier B, diff-only)

Core: a draft built in the real Builder screen, saved through Save Draft against the real API, reopens from the saved
list with identical legs, planned entries and capture times.
Proof: re-run the core e2e yourself on ofo_dev's real catalogue; the builder's report is a claim.

Model: sonnet (Tier B reviewer).
Budget: 30 min wall-clock, 30 tool calls (verifier maxTurns 40; batch commands).
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), then the JSON block below.

## Where
- Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-071`, branch `build/W-071-save-draft` at 6bf7092 (main merged in).
  Read-only. Diff: `git diff origin/main...HEAD`.
- Briefs: `docs/process/brief-W-071-r2.md` (the checklist) and `brief-W-071-r3.md` (ofo_dev proof). Work item
  `work/W-071.md` (card correction: `contract_id` on catalogue contracts, segment/token on saved legs, ADR-057).
- AC: REQ-038 AC-5 - get its fingerprint with `python tools/ac_fp.py REQ-038 AC-5`.

## Spec basis
- REQ-038 AC-5: "Each leg's planned entry price and its capture time are part of the definition and are saved with it"
- ADR-057: "A strategy leg, an order and an audit record link to the stored contract (its internal id), never to the raw token"
- ADR-068 (1): "it changes only when the user asks to reprice, never with the live price"

## Check (how could it fail?)
1. Re-run the core e2e on ofo_dev (the API through the orchestrator's `dev_run.py` wrapper named in the r3 brief, port
   8000; `npm run build`; `vite preview` on 4173 with `OFO_API_TARGET=http://127.0.0.1:8000`;
   `E2E_DEV_CATALOGUE=1 npx playwright test e2e/strategy-save-draft.spec.ts`), and without the flag (skipped with reason).
2. Does the e2e compare EVERY leg field and the planned entry + capture time, saved vs reopened? Does reopen ever call
   the planned-entry capture (re-capture)? The e2e stubs planned-entry capture (no live ticks on ofo_dev): is anything
   else stubbed that hides a real defect?
3. POST body keys per leg exactly: `contract_id`, `action`, `quantity` (lots x lot size), `planned_entry`,
   `captured_at` - no live price, no instrument id.
4. The two backend fields are additive (existing responses unchanged otherwise); OpenAPI drift test green.
5. A pre-ADR-075 draft (no entries): what does the screen show? (Builder: `reason_code: needs_reprice` + the draft
   label, no prompt text because no catalogue template exists.) Is that an honest PARTIAL against the work item?
6. Route tests via `python scripts/orchestrator/db_run.py D:\Abhay\Ventures\OptionsForOptions2-W-071 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_catalogue_picker_api.py tests_app/test_strategy_store.py tests_app/test_openapi_drift.py`
   from the main checkout; `npx vitest run` in `frontend/`.
Stop every server you start by PID.

## Return
Evidence table, then one JSON block:
```json
[{"ac": "AC-5", "requirement": "REQ-038", "ac_fp": "<from ac_fp.py>", "result": "pass|fail",
  "commands": "...", "observed": "...", "attack": "..."}]
```
Plus defects (file:line, severity).
