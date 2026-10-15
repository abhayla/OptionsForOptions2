# Builder brief: #242 atool selects the tests_app files a route / response-model change can break (Tier B)

Core: given PR #241's backend diff (before its fix round), a selector picks `tests_app/test_response_door.py` and
`tests_app/test_strategy_planned_entry.py` - the two files that went red in CI - and does NOT pick unrelated files.
Proof: step 1 is a test that feeds the selector the real #241 backend diff (saved as a fixture) against the repo's real
`tests_app/` folder and asserts the selected set. Write it FIRST, red, then build.

Tier: B. Model: sonnet.
Budget: 30 min wall-clock, 40 tool calls. This is a HARD limit: count your calls; at call 37 commit what you have,
push, and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - orchestration tooling of this repo, not product code (the legacy-reuse map covers the app only).

## Basis
- Issue #242 (mechanism for finding `targeted-tests-miss-dependent-files`, 4th occurrence). Its proposal: for every
  changed file under `backend/ofo_app/routes/` or `backend/ofo_app/*store*.py`, collect route paths and response-model
  names, grep `tests_app/`, run the matching files.
- Why targeted at all: the test database `ofo_test` sits on the host that also serves IPODhan production; the full app
  suite (~15 min, 488+ tests) runs only in CI. A selector that picks most of `tests_app/` defeats the rule - the last
  fix round ran 11 files / 488 tests there; that is the failure to avoid.

## Start
- Branch `build/242-atool-route-selector` from current main.
- Read `scripts/orchestrator/atool.py` (the existing migration selector, lines 39-56, is the pattern to follow),
  `tests/orchestrator/test_check_brief.py` (test style), `backend/ofo_app/routes/strategies.py`,
  `backend/ofo_app/routes/catalogue.py`.
- Find PR #241's feature commit(s) before its fix round: `gh pr view 241 --json commits`; the fix round is commit
  `2e317c2` ("fix the two tests that pinned the strategy response"). Take `git diff <base>..<last commit before
  2e317c2> -- backend/` as the fixture.

## What to build
1. `scripts/orchestrator/select_app_tests.py`: a pure function `select(changed_files, diff_text, tests_dir) -> list`
   plus a CLI. Precision first: key on what the diff CHANGED (the response-model classes and route paths whose
   definition or body has a +/- line in a hunk), not on every name defined in a touched file. Match a test file when
   it names one of those models, or calls one of those exact route paths (a path string such as `"/strategies"` or
   `f"/strategies/{...}"`). Measure and report: how many files each key selects.
2. Wire it into `atool.py --no-tests` next to the migration step: run the selected files through `db_run.py` exactly as
   that step does; print `route tests (N files) rc ...`; print the selected names. N = 0 runs nothing.
3. `tests/orchestrator/test_select_app_tests.py` + fixture `tests/orchestrator/fixtures/pr241-backend.diff`:
   - the #241 diff selects both red files;
   - it selects NOT `tests_app/test_catalogue_load*.py` (or whatever the catalogue-loading tests are named - name them
     in the test) and the selected set has at most 6 files - report the exact set and count in your evidence table;
   - a diff touching no route/model selects nothing; a diff that only edits a comment in a route file selects nothing.

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutations: select every file that mentions any path in a touched route file (must fail the at-most-6 assert); drop
  response-model matching (must lose one of the two red files - check which key catches each, and say so); ignore the
  hunk and use the whole file.
- Fail closed: a diff the parser cannot read (binary, rename only) prints `route tests: diff not parsed - run the
  route files by hand` and makes atool exit non-zero, never a silent 0 files.
- Tests are pure (no DB, no network, no git calls in the unit test - the fixture carries the diff), so the kit CI
  runs them.

## Rules
- Only `scripts/orchestrator/` and `tests/orchestrator/` change. No kit file (`tools/`, `.claude/`), no `spec/`, no app
  code. Never write `evidence/`.
- Do not run `tests_app` against ofo_test in this item, except ONE run of atool's new step on this branch if it selects
  0 files (it should: this branch changes no route) - that proves the wiring without touching the database.
- Run `python -m pytest -q -p no:cacheprovider tests/orchestrator` and the repo guard tests
  `python -m pytest -q -p no:cacheprovider tests/test_*.py`. Long output to a log file, tail only.
- Commit and push `build/242-atool-route-selector`. Do not open a PR.
