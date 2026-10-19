# Builder brief: W-089 Settings -> Broker & Market Data - Tier B

Common brief: docs/process/builder-brief.md
Core: a status route reports the four connection statuses from real stored state, and the settings page shows them
with last sync, Reconnect and Disconnect.
Proof: tests_app/test_broker_status_route.py on the test database: with a stored session -> Connected rows; with the
session ended -> Disconnected with the guide; frontend/e2e/broker-settings.spec.ts shows both. (The ofo_dev run with
the owner's session is GC-3F's, not tonight's: no live run.)
Spec basis: REQ-015 AC-4, AC-8; REQ-051 AC-1; ADR-020; work/W-089.md.
Copy from: the algochanakya map row for src/components/settings/KiteSettings.vue (ADAPT, no token in URL) in
spec/technical-design/legacy-reuse.md.
Findings checked: liveness-from-a-file-nobody-deletes, liveness-from-shared-subscribers, secret-filter-by-key-name, staleness-by-last-change-age
Threat model: in scope - the status route never returns a token, key or secret, and Disconnect needs the signed-in owner; out of scope - Kite's own login page.
Tier: B. Branch: build/W-089-broker-settings from origin/main.
Budget: 75 min wall-clock, 80 tool calls
Report: evidence-table

## Facts on main
- Disconnect = backend/ofo_app/broker_token_store.py:103 end_session(reason='disconnected'); there is no function
  named disconnect. Disconnect keeps strategies, history, entitlements and the account (REQ-015 AC-8): test that rows
  in those tables are untouched.
- The settings route /settings/broker-market-data is a Placeholder in frontend/src/router/routes.js; replace only that
  route. Do NOT change routes/broker.py's login or callback handlers (GC-3L logs in through them on Monday): add the
  status/disconnect endpoints in a new module or as new handlers only.
- Live feed status: read the existing live-market state; if it cannot say Connected without a subscribed screen, the
  page says so (Partially connected, naming what to fix) - never Connected by default.

## Attack cases
1. The status reply contains no access token, api key or secret (allow-list of reply keys, generated test).
2. Disconnect by an anonymous caller -> refused.
3. A stale session (older than today's Kite expiry) -> not Connected.
4. Disconnect then status -> Disconnected; strategies and history rows unchanged.

B4: (a) n/a; (b) n/a; (c) the reply-key check is an allow-list; (d) each status state (connected, partial,
disconnected, unknown/error) has a test and a stated page text.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only;
no regenerated files in the PR except docs/api/openapi.json.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: tests_app/test_broker_status_route.py and tests_app/test_broker_disconnect.py through
scripts/orchestrator/db_run.py (targeted files only); in frontend/: npm run lint, npm run test:run.
