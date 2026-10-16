---
work_item: W-087
ac: AC-1
requirement: REQ-001
ac_fp: "4c34eee648d2"
result: pass
verified_by: "verifier (sonnet/high, fresh context, docs/gc-1-closeout b643356)"
builder: "none (verify-only card; code on main)"
date: '2026-10-16'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_safety_checks.py (plus the other linked domain targets); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_followups.py; python tools/ac_fp.py REQ-001 AC-1 --yaml; python -c (pydantic annotations of routes.strategies/outcome/catalogue/planned_entry; StrategyIn BANKNIFTY); python -c (parse_instruments_stream + Catalogue.load with a BANKNIFTY row); Grep frontend/src UNDERLYINGS"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_safety_checks.py (plus the other linked domain targets); python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_followups.py; python tools/ac_fp.py REQ-001 AC-1 --yaml; python -c (pydantic annotations of routes.strategies/outcome/catalogue/planned_entry; StrategyIn BANKNIFTY); python -c (parse_instruments_stream + Catalogue.load with a BANKNIFTY row); Grep frontend/src UNDERLYINGS
observed: 175 passed (domain); 43 passed, 7 skipped (tests_app, DB-gated); safety check test expects 'BANKNIFTY is not supported. Supported underlyings: NIFTY, SENSEX.' (CheckCode.UNDERLYING_UNSUPPORTED); 10 request/response models annotate underlying as Literal['NIFTY','SENSEX']; legPicker.js UNDERLYINGS = ['NIFTY','SENSEX'] feeds the only <select>; catalogue load kept ['NIFTY'] out of a BANKNIFTY+NIFTY list; migration 0008 has a NIFTY/SENSEX CHECK (read, not run)
attack: BANKNIFTY submitted to StrategyIn: literal_error on 'underlying'. BANKNIFTY instrument row passed to Catalogue.load: dropped, only NIFTY loaded. The picker cannot offer a third value (list is a 2-entry const, backend refuses anyway). Gaps: DB-backed BANKNIFTY API tests skipped (no database here), and no frontend test asserts the 2-entry picker (source-read only). Judged pass from the domain test plus code reading.

Recorded by the orchestrator from the verifier's returned block.
