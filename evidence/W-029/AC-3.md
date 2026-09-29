---
work_item: W-029
ac: AC-3
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_sink_backup_checks.py; verifier mutants M7 (underlying condition removed) and M14 (group room check disabled); full suite after the orchestrator's card fix"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_sink_backup_checks.py; verifier mutants M7 (underlying condition removed) and M14 (group room check disabled); full suite after the orchestrator's card fix
observed: M7 -> test red (SendRefused 'the catalogue has 2 instruments'); M14 -> test red (DID NOT RAISE SendRefused); both green on restore; diff is test-only; full suite 1174 passed
attack: verifier failed the first check only because the builder's next_action edit had an unquoted colon that broke work/W-029.md YAML (test_spec_integrity failed, 1 failed / 1173 passed); the orchestrator restored main's card with a quoted next_action (card-only, class 1), after which lint is clean and the suite passes

Recorded by the orchestrator from the verifier's returned block.
