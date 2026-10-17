# Builder brief: mechanism for finding repo-wide-scan-outside-targeted-tests - a `repo_scan` pytest marker (Tier B: test tooling)

Core: `python -m pytest -q -p no:cacheprovider -m repo_scan tests` runs EVERY repo-wide scan test of the domain tree
(each test that reads the source of modules other than the one it tests - e.g. `tests/errors/test_producer_inventory.py`,
`tests/engine/test_pricing_scan.py`, `tests/test_no_wall_clock_asserts.py`, `tests/test_fixture_symbols.py`) in well
under a minute, and a collection-time check fails any scan-shaped test that lacks the marker.
Proof: on main's tree, the marked run collects >= the scans listed in the finding's occurrences (name them with their
counts in the report), and a scratch copy of one scan test with the marker removed makes the collection check red.

Tier: B. Model: sonnet.
Budget: 40 min wall-clock, 45 tool calls. HARD limit: at call 42 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, `git status --short` empty.
Copy from: none - pytest's own marker mechanism; `pytest.ini` / `pytest-app.ini` already declare a `network` marker
(the pattern).
Findings checked: repo-wide-scan-outside-targeted-tests, local-ci-mirror-runs-a-subset, targeted-tests-miss-dependent-files
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- Finding `repo-wide-scan-outside-targeted-tests` (detection note): "Open: a `repo_scan` marker on every repo-wide scan
  test so one fast command runs them all." (knowledge registry, not spec; no spec section governs test tooling -
  `Spec basis: none` for the product.)

## Build
1. Find the scans: grep `tests/` and `tests_app/` for tests that walk the source tree (`rglob`, `os.walk`, `glob(`,
   `ast.parse` over many files, `inspect.getsource` over modules other than one under test). List each with the
   reason it is a scan.
2. Mark each with `@pytest.mark.repo_scan` (or `pytestmark` per file); declare the marker in `pytest.ini` and
   `pytest-app.ini`. App-tree scans that need a database stay in `tests_app/` and are marked too (they run in CI;
   the domain ones run locally in one command).
3. The collection check: a test (in `tests/`, itself marked `repo_scan`) that parses every test file under `tests/`
   and `tests_app/` with `ast` and fails when a test function body (or its module) walks the source tree (the shapes
   from step 1 - an allow-list of the scan helper calls you found, not a guess) and carries no `repo_scan` mark. Red
   then green on a scratch file under `tmp_path`.
4. `scripts/orchestrator/check_brief.py`: a brief's `Tests:` line must also contain `-m repo_scan` (keep the three
   existing literals; add the fourth); update `tests/orchestrator/test_check_brief.py` red-then-green and the guard
   line in `docs/process/builder-brief.md`.

## Reviewer checklist
- Every scan named in the finding's occurrences is marked (producer inventory, pricing scan, broker-identifier column
  rule).
- The collection check fails on an unmarked scan in a scratch file, and passes on main's tree.
- `-m repo_scan` run time printed.

## DB
Not the shared-DB holder; run no DB command.

## Rules
- Branch `build/repo-scan-marker` from origin/main. No work card (a process mechanism, like GC-2c's atool_restore).
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
