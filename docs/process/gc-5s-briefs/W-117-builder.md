# W-117 builder brief (GC-5S item 6): Learn, Alerts, Market context shells

Common brief: docs/process/builder-brief.md
Core: the Learn page lists the reviewed strategy templates from the one catalogue file through a read-only route, with no text retyped in the browser.
Proof: step 1 = a route test that reads all 21 templates from `GET /api/strategy-templates` with names and descriptions equal to `backend/ofo/strategy/catalogue.yaml` (loaded through the existing catalogue loader, never re-parsed), no database opened.
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Tier: B (display only; a read-only route over a static file; no money, no order, no DB).
Copy from: none - the catalogue loader already exists in `backend/ofo/strategy/` (reuse it); legacy-reuse.md row 112 (`seed_strategies.py`) is already adapted into catalogue.yaml.
Design basis: docs/design/screens-research-2026-10-19.md sections `Learn`, `Alerts`, `Market context` and `Orchestrator decisions on this note`.

## Spec basis (quoted)
- REQ-011 AC-1: "Learn contains strategy education, options concepts and platform guidance."
- REQ-009 AC-6: "Alerts: Active, History, Notification settings."
- REQ-009 AC-4: "Market: Option Chain, Underlying/index view, Market context."
- Wording rule (ADR-114 note in REQ-011): lesson wording is owner-reviewed, so the screens show ONLY texts that already
  exist and were reviewed (the catalogue's `name` and `description`); no new teaching text.

## What to build
1. Backend: `GET /api/strategy-templates` -> `{templates: [{id, name, description, level, views, objectives}]}` from the
   existing catalogue loader (find it: grep `catalogue.yaml` under `backend/ofo/strategy/`). New `ApiModel`s registered in
   `tests_app/test_response_door.py`; regenerate `docs/api/openapi.json`. No database dependency on this route.
2. Learn (`frontend/src/router/nav.js` Learn entries): tab Strategy education = the templates grouped by `level`
   (Beginner first), each card name + description + market views as given; Options concepts and Platform guidance tabs
   each show one line `Nothing published here yet.` (no placeholder lessons).
3. Alerts (Active / History / Notification settings entries): Active and History each show
   `No alerts yet. Alerts start when strategy monitoring rules are added.`; Notification settings shows
   `No notification channels are set up yet.` No buttons, no fake rows.
4. Market context: the W-115 `IndexStrip.vue` (import it) and one market status line from the index answer's state
   (live / not live) - no PCR, OI totals, VIX or any figure the API does not send.
5. Every page: no money, no order or execute link (ADR-002), decision-support wording only (ADR-003).

## Tests (targeted only)
- `tests_app/test_strategy_templates_route.py` (no DB): AC-1 21 templates, ids unique, every name/description equal to
  the loader's values (expected values from the loader, not typed), unknown query params ignored per the app's rule.
- `frontend/tests/learn.test.js`: AC-1 cards from a fake route reply grouped by level, texts rendered as given; the two
  empty tabs show their line; Alerts and Market context pages render their states; Market context shows no number when
  the index answer is not live (reuse the composable's behaviour; finding last-live-answer-kept-after-drop).
- Run: `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_templates_route.py
  tests_app/test_response_door.py` (if test_response_door opens a database it is collected only and runs in CI), `npm run
  lint`, `npx vitest run tests/learn.test.js`, `npm run build`, the brief's `Tests:` line, `python scripts/ruff_ratchet.py`.

## Standing items (B4)
(a)-(c) n/a; (d) states: route ok, route failed (each page shows the server's error), empty catalogue, index live / not
live. No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR except `docs/api/openapi.json`.

## Isolation (hard rules)
Work ONLY in `D:\Abhay\Ventures\OptionsForOptions2-gc5s-w117` (branch `build/W-117-shells`, stacked on W-115's pushed
branch; `work/W-117.md` untracked there - commit it; add its row `W-117: 4b           # GC-5S: Learn / Alerts / Market
context shells (REQ-011 AC-1 part)` to `docs/process/coverage-stages.yaml`). Never run git or npm in
`D:\Abhay\Ventures\OptionsForOptions2`; no database, no API server, no Playwright run; never touch ports
8765/4173/8766/4174, migrations or execute/order files. Commit, push; do NOT open a PR.
