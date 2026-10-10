---
work_item: W-067
ac: AC-3
requirement: REQ-051
ac_fp: "152cff673a54"
result: pass
verified_by: "verifier (opus, fresh context, 2026-10-10: AC-3 at 90633d0, AC-4/AC-5 re-check at 1dd86dc)"
builder: "builder (sonnet; rounds 1-3, 2026-10-10)"
date: '2026-10-10'
commands: "(verifier 1, at 90633d0; head 1dd86dc changes only work/W-067.md) python tools/ac_fp.py REQ-051 AC-3 --yaml; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_pg_store.py tests_app/test_history_finalize_job.py tests_app/test_history_nonblocking.py tests_app/test_history_finalize_scale.py tests_app/test_history_finalize_start.py tests/history/test_recorder_queue.py; python -m pytest -q -p no:cacheprovider tests/history tests/execution/test_safety_checks.py tests/test_no_app_imports.py tests/test_no_wall_clock_asserts.py tests/marketdata/test_provider_replaceable.py; db_run.py <wt> python probe_w067.py; db_run.py <wt> python mut_w067.py"
---

AC: AC-3
result: pass
commands: (verifier 1, at 90633d0; head 1dd86dc changes only work/W-067.md) python tools/ac_fp.py REQ-051 AC-3 --yaml; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_history_pg_store.py tests_app/test_history_finalize_job.py tests_app/test_history_nonblocking.py tests_app/test_history_finalize_scale.py tests_app/test_history_finalize_start.py tests/history/test_recorder_queue.py; python -m pytest -q -p no:cacheprovider tests/history tests/execution/test_safety_checks.py tests/test_no_app_imports.py tests/test_no_wall_clock_asserts.py tests/marketdata/test_provider_replaceable.py; db_run.py <wt> python probe_w067.py; db_run.py <wt> python mut_w067.py
observed: 46 passed (0 skipped); 247 passed; role: ofo_app; on final day: update close / kite->backfilled / kite->live / live->kite / removed=TRUE / insert / status->provisional all 'refused OF009'; delete 'refused 42501'; insert 1.001 'refused 23514'; store put on final day -> refused_final 2, day unchanged True; paisa 1.001 refused, 1.010 accepted; core test: engine-disposed readback == in-memory store bar by bar on the real 2026-10-08 frames
attack: Tried as ofo_app, inside rolled-back savepoints, to mutate a final day in seven ways: every one refused by the DB guard. Tried a 3-decimal price through the store and through raw SQL: both refused. A price with trailing zeros (1.0100000) is accepted as whole paise. Mutation M3 (import ofo_app in a tests/ file) turned test_no_app_imports red. Not attacked: the 5-minute and daily on-demand derivation (W-062 scope), beyond the domain suite passing.

Recorded by the orchestrator from the verifier's returned block.
