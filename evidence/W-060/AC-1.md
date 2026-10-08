---
work_item: W-060
ac: AC-1
requirement: REQ-072
ac_fp: "cbc9e9db983e"
result: pass
verified_by: "verifier (sonnet, fresh context, real test database)"
builder: "builder (opus/sonnet W-060 rounds 1-4; sonnet main repair PR 149)"
date: '2026-10-08'
commands: "git worktree add --detach <SCRATCH>/verify/W-060a1 origin/main (017478e); python -m pytest -q -p no:cacheprovider tests/instruments/test_index_segments.py tests/instruments; python -m pytest -q -p no:cacheprovider; db_run.py (ADR-048 test database on the VPS via the tunnel) python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_index_rows_store.py tests_app/test_catalogue_store.py; db_run.py python -c <rolled-back ofo_app insert attacks>"
---

AC: AC-1
result: pass
commands: git worktree add --detach <SCRATCH>/verify/W-060a1 origin/main (017478e); python -m pytest -q -p no:cacheprovider tests/instruments/test_index_segments.py tests/instruments; python -m pytest -q -p no:cacheprovider; db_run.py (ADR-048 test database on the VPS via the tunnel) python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_index_rows_store.py tests_app/test_catalogue_store.py; db_run.py python -c <rolled-back ofo_app insert attacks>
observed: domain 8 passed; full suite 2550 passed; database tests 102 passed, 0 skipped (no SKIPPED lines) against real PostgreSQL 16.8; NIFTY 50 (NSE_INDEX, 1001) and SENSEX (BSE_INDEX, 1) stored and read back through load_catalogue; token 1001 held exactly one row inside the transaction, 0 index rows after rollback
attack: Inserted as ofo_app in a rolled-back transaction: NIFTY 50 with token 1002, with SENSEX's token 1, SENSEX with 1001, with an expiry, with a strike, the cash row's name on NSE_INDEX 1001, INDIA VIX as a third index -> each refused SQLSTATE 23514 by catalogue_contracts_index_identity; NIFTY 50 typed CE -> catalogue_contracts_instrument_type_check. The NSE cash row sharing exchange token 1001 is skipped by the parser in both orders and its token 256266 is unmapped (F-10). Outside AC-1, named in the migration: a hand-written broker row under 'INDICES' with lot 0 is refused only by the store (issue #156).

Recorded by the orchestrator from the verifier's returned block.
