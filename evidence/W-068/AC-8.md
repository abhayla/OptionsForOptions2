---
work_item: W-068
ac: AC-8
requirement: REQ-035
ac_fp: "1d28e06c4ec2"
result: pass
verified_by: "verifier (sonnet, fresh context, 2026-10-10, at 115a352; an earlier pass at 7335694 failed on the CI e2e race fixed in ce19126)"
builder: "builder (sonnet; rounds 1-3 + fixes, 2026-10-10)"
date: '2026-10-10'
commands: "python tools/ac_fp.py REQ-035 AC-8 --yaml --root <wt>; python -m pytest -q -p no:cacheprovider tests/outcome/test_planned_entry.py tests/engine/test_pricing_scan.py; python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_catalogue_picker_api.py; db_run.py . pytest -c pytest-app.ini tests_app/test_catalogue_load_command.py; npx vitest run tests/leg-picker.test.js; gh pr checks 194; gh run view 38067727132 --log"
---

AC: AC-8
result: pass
commands: python tools/ac_fp.py REQ-035 AC-8 --yaml --root <wt>; python -m pytest -q -p no:cacheprovider tests/outcome/test_planned_entry.py tests/engine/test_pricing_scan.py; db_run.py . pytest -c pytest-app.ini tests_app/test_catalogue_picker_api.py (includes the network test on Zerodha's real list); db_run.py . pytest -c pytest-app.ini tests_app/test_catalogue_load_command.py; npx vitest run tests/leg-picker.test.js; gh pr checks 194; gh run view 38067727132 --log
observed: 59 passed; 15 passed (no skips); 6 passed; 26 passed; CI api/coverage/frontend/lint-and-test all pass; Playwright leg-picker.spec.ts 3 tests x 2 viewports all passed first time, 168 passed, no retry/flaky lines
attack: (1) Expired, retired, delisted or not-currently-listed contracts leaking into the picker: the query requires NOT retired, NOT delisted, currently_listed and expiry >= the database clock's IST date; tests prove a not-currently-listed row is not offered, an expiry equal to today is offered and yesterday's is not, and another underlying is excluded. (2) The e2e race that failed the previous pass: edit/remove and price-less tests passed first time on both viewports. (3) An invented price for a leg with no live quote: planned-entry tests assert null for no quote, a disconnected provider and no provider; the e2e checks the not-connected wording with no numbers. No break found. Not checked: a mutation test of the SQL guards; a local Playwright run (load cap).

Recorded by the orchestrator from the verifier's returned block.
