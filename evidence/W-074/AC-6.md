---
work_item: W-074
ac: AC-6
requirement: REQ-032
ac_fp: "080da64fa2a1"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "pytest tests/charges (v074 @1e5e6f0); db_run.py pytest -c pytest-app.ini tests_app/test_charge_rates_store.py tests_app/test_migration_sql_parses.py; inline hand-compute + guard attack script; ac_fp.py REQ-032 AC-6 --yaml"
---

AC: AC-6
result: pass
commands: pytest tests/charges (v074 @1e5e6f0); db_run.py pytest -c pytest-app.ini tests_app/test_charge_rates_store.py tests_app/test_migration_sql_parses.py; inline hand-compute + guard attack script; ac_fp.py REQ-032 AC-6 --yaml
observed: 84 passed; 468 passed; SELL NIFTY26O1923150CE 53.3x65 and BUY NIFTY26O1922550PE 34x65 hand-computed = Kite reply = calculator on every component (stamp: ours 0.0663 vs Kite 0, stated)
attack: stt 0.15 / nse 0.03553 / gst 18 refused in code + DB CHECK; float/0/neg/Inf price refused; same-date, back-dated, race refused; future set not in force; incomplete later date ignored (no mixed answer); UPDATE/DELETE refused. Gap: stamp 0.003 and sebi 0.0001 typed as percentages accepted (D1, MINOR, carried into W-075). Scope: AC-6's charges half only; margin-planning not checked (REQ-032 already Verified for it).

Recorded by the orchestrator from the verifier's returned block.
