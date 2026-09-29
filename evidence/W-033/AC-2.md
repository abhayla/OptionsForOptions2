---
work_item: W-033
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py tests/execution/test_plan.py tests/reconciliation/test_compare.py tests/strategy/test_builder_history.py tests/timeline/test_timeline.py tests/test_no_wall_clock_asserts.py; python -m pytest -q -p no:cacheprovider; in-process monkeypatch mutants (calls|inline|verify); guard run against git show main:<file>"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py tests/execution/test_plan.py tests/reconciliation/test_compare.py tests/strategy/test_builder_history.py tests/timeline/test_timeline.py tests/test_no_wall_clock_asserts.py; python -m pytest -q -p no:cacheprovider; in-process monkeypatch mutants (calls|inline|verify); guard run against git show main:<file>
observed: 121 passed; full suite 1273 passed; real call ratio ~1.95-2.35 (limit 2.5); a per-element-call quadratic mutant made test_one_thousand_history_appends_stay_fast fail with 'not linear'; the guard flags the 5 old lines (246, 238, 406, 301, 99) on main and passes now
attack: Quadratic mutants: a per-element-call one is caught; an inline list-comprehension one passes (gap, ~7 ms at 1000, the old wall-clock thresholds would not have caught it either). Compare test no longer checks strategies scaling; a real quadratic exists in backend/ofo/reconciliation/compare.py ~line 368 (3.5x calls for 100->200 strategies), reported as a finding. Guard misses timeit, datetime.now() differences, 'import time as t' and named-constant thresholds. Card defect (class 1): the guard could not claim REQ-038 AC-2; corrected by the orchestrator in the same PR.

Recorded by the orchestrator from the verifier's returned block.
