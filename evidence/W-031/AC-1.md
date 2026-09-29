---
work_item: W-031
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "git diff origin/main...origin/build/W-031-fixture-symbols; python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py tests/marketdata/test_quote.py tests/marketdata/test_rule_health.py tests/range/test_pick_lists.py; grep of tests/fixtures/instruments/instruments_slice.csv for NIFTY26O0623500CE and NIFTY26O06{20000,20100,20500,20700,20800,20850,20900,20950,21000,21200}CE; python -m pytest -q -p no:cacheprovider; python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py"
---

AC: AC-1
result: pass
commands: git diff origin/main...origin/build/W-031-fixture-symbols; python -m pytest -q -p no:cacheprovider tests/test_fixture_symbols.py tests/marketdata/test_quote.py tests/marketdata/test_rule_health.py tests/range/test_pick_lists.py; grep of tests/fixtures/instruments/instruments_slice.csv for NIFTY26O0623500CE and NIFTY26O06{20000,20100,20500,20700,20800,20850,20900,20950,21000,21200}CE; python -m pytest -q -p no:cacheprovider; python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py
observed: 58 passed on the guard plus the 3 touched files. Replaced symbols exist at expiry 2026-10-06 in the catalogue slice. Diff removes only 3 ALLOWLIST entries and swaps symbol/expiry strings, no assertion changed. Full suite 1217 passed, 1 failed (tests/strategy/test_versions.py::test_one_thousand_history_appends_stay_fast, a timing test); it passed on re-run (30 passed). No evidence/ or work/ files in the diff.
attack: Looked up the strikes the pick-list tests build (20000..20700). None are in the catalogue at any expiry, and the guard still passes because it only checks the f-string head (a real detection gap). The tests' assertions come from a self-built Catalogue, not the CSV, so they do not depend on catalogue membership. No explicit 'illustrative' note exists, only a 'synthetic' docstring at line 84, so issue #51's optional note is only partly met. Recorded as a finding, not a fail.

Recorded by the orchestrator from the verifier's returned block.
