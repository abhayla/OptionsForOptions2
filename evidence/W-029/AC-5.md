---
work_item: W-029
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_sink_backup_checks.py::test_guard_binding_mismatch_is_refused; verifier mutant M15"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_sink_backup_checks.py::test_guard_binding_mismatch_is_refused; verifier mutant M15
observed: M15 (binding comparison removed) -> test red (DID NOT RAISE GuardRefused); green on restore; full suite 1174 passed after the card fix
attack: same card-YAML note as AC-3

Recorded by the orchestrator from the verifier's returned block.
