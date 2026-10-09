# Builder brief: W-066 - outcome text from the catalogue, no W-024 exemption (issue #151)

Core: the real outcome of the W-063 NIFTY iron condor (replay frames 2026-10-08), at all three UX levels and with no
provider, serializes with every user-facing text field rendered from a catalogue template with typed slots, and the
W-024 response and error-boundary tests pass with the outcome route's exemption deleted.
Proof (step 1): a test walking the real outcome response in replay mode asserts every text field is a catalogue render
and that `tests_app/test_api_models.py` and `tests_app/test_error_boundary_scan.py` pass with `EXEMPT_ROUTES` /
`EXEMPT_FILE` removed - run red against 6bac774 first (12 plain `str` fields, issue #151), then green.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Commit after each numbered step; at budget stop after a commit and report
done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - the catalogue, `render_explanation`, `ApiModel` and the boundary are this project's own (W-024).

## Spec basis
- REQ-034 AC-7: "Outcome numbers appear in plain language first — 'What can I lose? What can I make? Where do I start losing?'"
- ADR-003 decision: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots."
- Wording: decision-support only (ADR-003 forbidden words and phrases; the catalogue's own checks enforce them).

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-066`, branch `build/W-066-outcome-catalogue`, stacked on
  `build/W-065-live-push` at 6bac774 (W-065 added `outcome_response()` in `routes/outcome.py`, shared by REST and the
  push). The orchestrator put `work/W-066.md` and this brief there: commit both first.
- Read: `gh issue view 151` (the probe of the 12 fields), `backend/ofo_app/routes/outcome.py`,
  `backend/ofo_app/api_models.py` (ApiModel, Identifier, the closed value types), `backend/ofo/outcome/serialize.py`
  and `service.py`, `backend/ofo/errors/templates.py` + `catalogue.py` (`render_explanation`, pins in
  `tests/errors/template_pins.json`), `tests_app/test_api_models.py`, `tests_app/test_error_boundary_scan.py`,
  `tests_app/test_outcome_route.py`.

## What to build (issue #151's five items)
1. Every outcome / table / summary text minted through `render_explanation` with new catalogue templates and pins:
   status label, reason, margin reason, the three plain-language summary sentences (AC-7: what can I lose, what can I
   make, where do I start losing), scenario label, column labels, cell display, cell reason, leg label. Money and points
   go into typed slots as the existing money/points string types, never pre-formatted into free text.
2. An `InstrumentId` type (closed pattern `SEGMENT:digits`, e.g. `NSE_FO:44595`) instead of `Identifier` for
   instrument ids.
3. Numbers as the money/points string types; codes as closed `Literal`s.
4. Errors raised through the boundary; no `HTTPException` in the route.
5. Delete the outcome exemption from both tests (`EXEMPT_ROUTES`, `EXEMPT_FILE`, and the tests that pin it); both
   tests green with no exemption. The W-065 `outcome_response()` keeps serving REST and the push from one function.
List every new template line in `docs/process/w024-templates-for-owner.md` ("pending owner read").

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutation: return one summary sentence as a plain `str`; put a pre-formatted "₹8,245.25" into a text slot instead of
  the money type; widen `InstrumentId` to allow a space; re-add the exemption; raise `HTTPException` in the route.
- The W-063 numbers stay exact in the rendered sentences (max loss 8,245.25, max profit 4,754.75, breakevens
  22,326.85 / 22,873.15) - expected values written literally, never computed by running the code.
- Every new template passes the ADR-003 forbidden-word checks of the catalogue.

## Rules (this PC is the Windows VPS that also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted tests only; NEVER the full app suite, Playwright, npm or `tools/ci_local.py`. From
  `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-066 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_route.py tests_app/test_api_models.py tests_app/test_error_boundary_scan.py tests_app/test_strategy_live_push.py tests_app/test_replay_mode.py`.
  Domain: `python -m pytest -q -p no:cacheprovider tests/outcome tests/errors tests/table` (from the worktree).
  No alembic. Frontend: the screen (W-064) reads these fields - if a field's JSON shape changes, list it in the report;
  do not run npm here (CI runs the frontend job).
- Kit checks: `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-W-066 W-066 --no-tests`;
  generated files: `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\regen.py C:\Abhay\Ventures\OptionsForOptions2-W-066`.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views; read them with Read/Grep.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified/reviewed. Start no servers.
- Commit and push `build/W-066-outcome-catalogue`. Do not open a PR.
