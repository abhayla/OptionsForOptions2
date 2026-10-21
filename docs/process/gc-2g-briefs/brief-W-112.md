# Builder brief: W-112 REQ-052 AC-1 - no historical market data shown to users (repo_scan guard) - GC-2g item 3, Tier B

Common brief: docs/process/builder-brief.md
Core: a repo_scan test proves that no API route and no frontend/src page serves or shows historical market data, by an
allow-list of the modules that may read history (internal only), and goes red on a planted route and a planted page.
Proof: the new test passes on origin/main; a planted FastAPI route that imports ofo_app.kite_history (or the history
store) and a planted frontend/src file that calls a history/candles API path each make it fail (mutation run in a
scratch copy, result lines in the report).
Spec basis: REQ-052 AC-1; ADR-066; F-33.

REQ-052 AC-1: "with no historical data shown to users"
ADR-066 is the decision that the history is internal use only (gap-filling, tests and replays).
Copy from: none - a new repo_scan guard test; the legacy-reuse map has no row for it.
Findings checked: guard-as-forbidden-list, repo-wide-scan-outside-targeted-tests, verified-on-a-module-the-product-does-not-call
Threat model: in scope - routes and pages (below); out of scope - internal jobs, tests, scripts (below).
In scope in full: an API route (any module the FastAPI app registers routes from) that imports or calls a
history reader (backend/ofo_app/kite_history.py, history_store.py, history_finalize.py, backend/ofo/history/*), and a
frontend/src file that requests a history/candles path or imports such a module; out of scope - internal jobs (the
recorder, the finaliser, replays under APP_ENV=test), tests, scripts, forged imports via importlib strings.
Tier: B (no money, a guard test only). Branch: build/W-112-history-not-shown from origin/main.
Budget: 45 min wall-clock, 50 tool calls
Report: evidence-table

## What to build
1. `work/W-112.md` (copy the frontmatter shape of work/W-110.md): requirement_ids [REQ-052], tier B, status todo,
   `tests_required`:
   - `AC-1: tests_app/test_kite_history.py`
   - `AC-1: tests/test_history_not_shown.py` (the new test; pick this name)
   core/proof as above; next_action: draft PR, one verifier pass. Run `python tools/factory_lint.py .` and
   `python tools/trace_check.py .` (bare commands) after writing it.
2. `tests/test_history_not_shown.py`, marked `repo_scan`, stdlib only (tests/ runs in the kit CI with only pyyaml,
   jsonschema, pytest - do not import FastAPI): parse with `ast`, never import the app.
   - ALLOW-LIST, not a forbidden list (finding guard-as-forbidden-list): the exact set of backend modules allowed to
     import a history reader is written in the test (today's importers: backend/ofo/broker/kite_endpoints.py and the
     history modules themselves - verify with a grep first and justify each entry in a comment). Any other importer
     fails. Assert that no module under backend/ofo_app/routes/ (and the app factory that includes routers) is in it.
   - frontend/src: no file contains a request to a path with `history` or `candle` in it, and no file imports from a
     history module; state the allow-list (expected empty) in the test.
   - A self-test: the scanner run on a planted string/tree in tmp_path flags both the planted route and the planted
     page (this is the test that dies if the scan is broken), and a docstring per test starting with `AC-1:`.
3. Run tests_app/test_kite_history.py only if it needs no database (check first); else leave it to CI and say so.

## Attack cases the reviewer/verifier will run
1. Add `from ofo_app.kite_history import ...` to a module under backend/ofo_app/routes/ -> red.
2. Add `import ofo_app.history_store as h` (alias form) and `from ofo_app import kite_history` -> red.
3. A Vue file with `fetch('/api/history/candles')` or an axios call to `/api/candles` -> red.
4. Remove the allow-list check -> the self-test goes red.

## B4 standing items
(a) no time-budgeted job is touched; (b) no new CI import (stdlib + pytest only); (c) the detector fails closed on
shapes it cannot resolve (a relative import, `importlib.import_module` with a non-literal - flag it, do not skip) and
names its guard by import source; (d) not applicable (no other system's answer).

Rules: no new duplicated literal; reuse the existing helper (look at tests/engine/test_pricing_scan.py and other
repo_scan tests for a shared scan helper first); ruff/mypy baselines must not rise; targeted tests only; no regenerated
files in the PR. Do not write under evidence/. Do not open a PR. Windows local pytest: add `-p no:metadata` (#403).
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
