# Builder brief: W-069 - one closed response door (#148, REQ-065 AC-2)

Core: one door through which EVERY API response body (and error body) is serialized, emitting only closed value
types.
Proof (your step 1, red first): a TestClient over `create_app()` against the real
`GET /api/broker/refusals/broker_state_invalid`. (a) It answers 200 and the body equals today's bytes. (b) The 4
hostile variants from the design's test plan, with the class check patched off, answer 200 WITH the sentence on main
(red). Commit that red test (marked xfail-strict or skipped with a reason that names the step) before writing the door.
After the door, (b) answers 500, body `internal_system_request_failed` with an `ERR-` reference, and the sentence is
absent from the bytes.

Tier: A. Model: sonnet. Budget: 75 min wall-clock, 80 tool calls. Commit after each migration step; at budget stop
after a commit and report done / not done / next command. Report: evidence-table
(`| Claim | Evidence (command run this turn) |`), under ~300 words, plus the guard -> killing-test list (below).
Worktree: `C:\Abhay\Ventures\OptionsForOptions2-W-069`, branch `build/W-069-response-door` (already created; work
only there; commit there; do NOT push - the orchestrator pushes).
Copy from: none - a new mechanism; the legacy map has no response-serializer row (algochanakya returns pydantic
models through FastAPI's own encoder, which is exactly what this item removes).

## LOAD CAP - this PC's PostgreSQL serves IPODhan PRODUCTION, and free RAM is about 2 GB
- Targeted test files only, one at a time, through `scripts/orchestrator/db_run.py` (set
  `OFO_GLOBAL_ENV=C:\Abhay\GLOBAL.env`). Every DB probe under 30 s. Never the full app suite, never Playwright, never
  `npm` anything - CI runs those. Send long output to a log file in the worktree and read its tail.

## The design is your spec for HOW
Read `docs/process/design-148-response-door.md` in full first and follow its sections 1-4 and its migration order
(section 3, steps 1-5; step 6 is NOT yours - it belongs to W-066). Additions since the design:
- W-068 added routers `backend/ofo_app/routes/catalogue.py` and `backend/ofo_app/routes/planned_entry.py`: move both
  onto `ClosedRoute` (between design steps 4 and 5). The design's "13 ApiModel subclasses" count is from before
  W-068; recount with grep and put EVERY app ApiModel subclass in the parity test and the leaf-table coverage test.
- ADR-073 (below): `/docs`, `/redoc` and `/openapi.json` are served only when APP_ENV is development or test and are
  exempt from the door there by exact path; in production they answer 404. Test both APP_ENV values.
- Out of scope: #148 MAJOR 2 (design section 5; owner question 8: its own round); the outcome route stays exempt
  (W-066 / #172); the MINORs in design section 5.

## Spec basis (quoted verbatim)
- REQ-065 AC-2: "Every user-facing error states what happened, the impact, what is blocked and the next action."
- ADR-003 Q226: "every platform message comes from a
  fixed, reviewed template catalogue with typed slots." (The door is how a response keeps to this: no text reaches a
  user except catalogue text and closed values.)
- ADR-073: "The framework-generated API docs page (/docs) and API description (/openapi.json) are served only when
  APP_ENV is development or test; there they are exempt from the closed response door by exact path. In production
  both answer 404."

## Reviewer checklist (Tier A; the reviewer mutates each of these - make each true and tested)
Every mutation in the design's section 4 "Mutations" list must turn a named test red:
`emit` falls back to `model_dump`; emits extras; uses aliases as keys; drop the Literal pattern; re-allow Enum; drop
the dict-key check; drop the Identifier re-check; `isinstance` instead of exact `type`; the wrapper passes any
Response; remove the seal check; one router without ClosedRoute; `_body` back to `JSONResponse`; allow NaN Money;
allow `model_config` overrides. Plus: `/docs` (or `/openapi.json`) served when APP_ENV=production must turn a test red.
Also checked:
- Expected bodies of existing routes are byte-identical (the temporary parity test, deleted at step 5 as the design
  says - keep a permanent golden-bytes test for at least the broker refusal route and one strategies route).
- The wrapper is async exactly when the original endpoint is (enumeration test).
- A refused response logs the field path and type name, never the value.
- `tests/` never imports `ofo_app` (guard `tests/test_no_app_imports.py`); every `tests_required` file in
  `work/W-069.md` exists.

## Guard -> killing test (report this list)
For every guard you write (`if ...: raise/refuse`), delete it in a scratch copy, run its test, name the test that
goes red. A guard with no killing test is unfinished work.

## Checks before you report (each as its own plain command, from the worktree root)
- `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py`
  then the same for `test_api_models.py`, `test_apimodel_closed.py`, `test_error_boundary.py`,
  `test_error_boundary_scan.py`, `test_health.py`, and the route test files of every router you moved (grep
  `tests_app/` for each route path and template code you touched - finding targeted-tests-miss-dependent-files).
- `python -m pytest -q -p no:cacheprovider tests/test_spec_integrity.py tests/test_no_app_imports.py tests/test_tests_required_exist.py tests/errors`
- `python scripts/generate_openapi.py --out <scratch file>` still works (development env).
Never pipe a check into `tail`/`head` before a commit (the project hook refuses it).
