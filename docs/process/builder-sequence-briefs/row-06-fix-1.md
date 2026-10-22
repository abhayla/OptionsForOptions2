# Row 6 fix round 1: REQ-048 AC-5 (W-134) - CI-safe tests, the bundle scan really runs, deep reply scan (Tier A, size M)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files; fix
lint as you go - no bulk `--add-noqa`; each noqa needs its own reason).

Core: the bundle and reply scans run in CI on the real build output and the real reply schemas, at every depth.
Proof: step 1 is a failing test that plants `access_token` inside the inline `ExecuteOut.basket` schema of a copy of
`docs/api/openapi.json`, which the current scan passes (verifier round 1 on 73212d26: `nested access_token in basket:
[]`); after the change it is red.

Spec basis: REQ-048 AC-5: "Browsers never connect to a vendor, never hold vendor credentials, never own authoritative
business rules and never decide execution eligibility (T1 #176)."
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. `.github/workflows/app-tests.yml` is PROJECT-owned
(CLAUDE.md: "The app job is .github/workflows/app-tests.yml (project-owned, separate from the kit's ci.yml)"); edit it
with the Edit tool only (a shell command naming that folder is refused by the kit guard); NEVER edit `ci.yml`. DB tests
through `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest ...`.
Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row06-fix1`.

## Verifier round 1 findings to fix
1. `tests_app/test_browser_never_decides_eligibility.py:53`: the three execute-claim tests answer 500 (Settings()
   raises without DATABASE_URL) in CI's api job, which sets only TEST_DATABASE_URL. Override the route's dependencies
   (`get_db`, `get_kite_session`) the way other execute tests do, or follow test_db_pool_startup.py's settings pattern;
   the test must pass with ONLY the CI variables set (prove it by running with DATABASE_URL unset).
2. The bundle scan never runs: `ci.yml` runs `tests/` with no frontend build; the frontend job in `app-tests.yml`
   builds but runs no pytest. Add, in the frontend job AFTER its build step, a Python setup + `pip install pytest` (if
   not present) + `python -m pytest -q -p no:cacheprovider tests/test_bundle_secret_scan.py`; make the scan FAIL (not
   skip) when `frontend/dist` is absent and `CI` is set (standing item b: the new step runs after the build and after
   its own dependency install).
3. `scan_openapi` reads only top-level `properties`: walk nested `properties`, `items`, `allOf`/`anyOf`/`oneOf` and
   inline objects recursively; key the allow-list by path (`ExecuteOut.basket.api_key`), each entry with a reason.
4. Bundle bypasses that pass today: bare `api.kite.trade`, `//api.kite.trade`, escaped `wss:\/\/`, a host split across
   two string literals, `https://localhost@api.kite.trade`, `ws://localhost:8000`, `apiKey=` camel case, a future
   `execute-*` chunk. Flag any vendor domain (`kite.trade`, `zerodha.com` except the exact allowed Kite basket/login
   URL prefixes) with or without a scheme, after un-escaping slashes; narrow `localhost`, `vuejs.org`, `www.w3.org` to
   the exact URL prefixes the real bundle holds (or remove them if they come only from comments/licences); narrow the
   chunk allow-list to the two current chunk name patterns; case-insensitive key-name matching. Base64 and run-time
   string building stay out of scope (static scan limit; ESLint is the second layer) - say so in the test docstring.

Attack list: (each names its test file)
1. `access_token` / `api_secret` planted at depth 2 and 3 of an inline response schema -> red
   (`tests/test_bundle_secret_scan.py`).
2. Each bypass in item 4 planted in a scratch bundle file -> red; the real `npm run build` output -> green (same file).
3. The execute-claim tests pass with DATABASE_URL unset and only TEST_DATABASE_URL set
   (`tests_app/test_browser_never_decides_eligibility.py`).
4. With `CI=true` and no `frontend/dist`, the bundle scan fails, not skips (`tests/test_bundle_secret_scan.py`).
5. The workflow step order: the new pytest step comes after the frontend build and after its own Python install
   (a small repo test reading `app-tests.yml`, `tests/test_app_workflow_bundle_scan.py`).

Standing items: (a) n/a: no time-budgeted job; (b) the new CI step runs after the frontend build and after its own
dependency install, and a repo test asserts that order; (c) both scans are allow-lists keyed by exact path or prefix,
fail closed on unreadable input; (d) n/a: no other system's answer.
Threat model: in scope - a vendor host/credential in a bundle or reply at any depth, a scan that silently skips in CI; out of scope - base64/run-time-built strings.
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted
Reviewer checklist: each round-1 finding has a test that was red before the fix; the CI step's order asserted; no
bulk noqa; every changed test file in full; scratch-copy mutation list; ruff baseline must not rise; targeted tests
only; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
