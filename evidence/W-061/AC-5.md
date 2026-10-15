---
work_item: W-061
ac: AC-5
requirement: REQ-038
ac_fp: "9b49fc3acd93"
result: pass
verified_by: "verifier (Opus, independent, Tier A, 2026-10-15)"
builder: "builder (Opus, issue #208, 2026-10-15)"
date: '2026-10-15'
commands: "db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head && current; db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_planned_entry.py; same runner on test_api_models.py test_response_door.py test_migration_sql_parses.py test_strategy_shape_matrix.py test_strategy_store.py test_strategy_closed_shape.py test_strategy_followups.py test_error_boundary_scan.py; db_run.py . python -c <rolled-back insert probe>; python -m pytest -q -p no:cacheprovider tests/strategy tests/errors; alembic downgrade -1 && current"
---

AC: AC-5
result: pass
commands: db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head && current; db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_planned_entry.py; same runner on test_api_models.py test_response_door.py test_migration_sql_parses.py test_strategy_shape_matrix.py test_strategy_store.py test_strategy_closed_shape.py test_strategy_followups.py test_error_boundary_scan.py; db_run.py . python -c <rolled-back insert probe>; python -m pytest -q -p no:cacheprovider tests/strategy tests/errors; alembic downgrade -1 && current
observed: upgrade 0010->0011_strategy_planned_entry (head); planned-entry file 18 passed; other files 767 passed / 63 failed, all environmental (62 'Catalogue update refused ... (ADR-058)', 1 test_strategy_store 0008 downgrade refused 'holds rows'); probe: 6-key and 8-key legs accepted, pair+ltp / planned_entry only / contract_id swapped for ltp (8 keys) / 44.901 / naive time / -1 all SQLSTATE 23514; domain 1016 passed; downgrade rc=0, current 0010_strategy_schema_version
attack: 8-key swap that beats a count-only check refused (0008 requires all six keys by name); one-sided, live-field, 3-decimal, zero/negative, naive and future entries refused (API 422 in test, DB 23514 in probe); reprice-only save writes 'planned entry prices repriced' history and restore returns the older entries; old draft returns keys absent; downgrade refuses while an entry is stored (test_0011). Covers the class: yes. Re-verifies REQ-038 AC-5 after ADR-075 changed its text (issue #208, PR from fix/208-draft-planned-entry). Unverified locally: shape-matrix files blocked by the shared-DB catalogue (CI judges them).

Recorded by the orchestrator from the verifier's returned block.
