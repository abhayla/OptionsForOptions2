# Fix brief: W-071 round 4 - stale OpenAPI file, the reprice prompt, one fragile template branch (Tier B)

Core: the saved-draft chain is proven (verifier: e2e green on ofo_dev at 1280/390, 0 re-captures on reopen); this
round closes the two gaps that failed it.
Proof: `tests_app/test_openapi_drift.py` green on the branch, and a vitest + e2e case where a draft saved without
planned entries reopens showing the reprice prompt.

Class: (1) every response-model change merged without regenerating `docs/api/openapi.json` - the builder reported "no
diff" from the generator; the verifier's drift test failed (`test_committed_openapi_matches_the_app`). (2) every
reopened draft whose legs have no planned entry (pre-ADR-075 drafts): today 100% show only the generic draft label
and no reprice prompt, although `legsFromSaved` sets `reason_code: needs_reprice`.
RCA: (1) the generator was run in a way that did not write the committed file (or its output was not committed);
(2) no component reads `needs_reprice`, and no catalogue message exists for it.

Tier: B. Model: sonnet.
Budget: 15 min wall-clock, 30 tool calls - a hard limit: count your calls; at 27 commit, push and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none - fixes inside W-071's own code.

## Spec basis
- REQ-038 AC-5: "Each leg's planned entry price and its capture time are part of the definition and are saved with it"
- ADR-068 (1): "it changes only when the user asks to reprice, never with the live price"

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-W-071`, branch `build/W-071-save-draft` at 6bf7092. Verifier report
items: `docs/api/openapi.json` stale (MAJOR); `frontend/src/lib/saveDraft.js:59` `needs_reprice` unused (work item
`work/W-071.md` objective: "reopens with entries missing and asks for a reprice"); `LegPicker.vue:~233` `v-else`
now follows the `captured_at` `v-if` instead of the `planned_entry` one (LOW).

## Fix
1. Run `python scripts/generate_openapi.py --out docs/api/openapi.json` (read the script first for its real flags),
   confirm `git diff --stat docs/api/openapi.json` shows the three new fields, commit, and run the drift test through
   `python scripts/orchestrator/db_run.py D:\Abhay\Ventures\OptionsForOptions2-W-071 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_openapi_drift.py`
   from `D:\Abhay\Ventures\OptionsForOptions2`.
2. Reprice prompt: a leg reopened with `needs_reprice` shows a catalogue message (the existing message catalogue, W-024
   rules: no free text in components) telling the user the leg has no planned entry and offering the existing
   reprice/capture action for that leg; nothing is captured until the user presses it. Wording is decision-support
   per ADR-003; a suggested text (not a spec quote): This leg was saved without a planned entry; reprice it to see
   its numbers. Vitest case + extend
   the save-draft e2e (or a unit-level test if the e2e cannot create a pre-ADR-075 draft through the API - say which).
3. Make the `LegPicker.vue` template branches explicit (unpriced label tied to `planned_entry`, capture time shown
   only with it); vitest covers both, either and neither.

## Rules
Targeted tests only; Playwright only `e2e/strategy-save-draft.spec.ts` with `E2E_DEV_CATALOGUE=1` against the API via
the `dev_run.py` wrapper (as in `docs/process/brief-W-071-r3.md`). Stop servers by PID. No kit, `spec/`, `evidence/`
edits. Commit and push `build/W-071-save-draft`; no PR.
