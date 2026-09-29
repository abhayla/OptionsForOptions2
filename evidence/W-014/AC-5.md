---
work_item: W-014
ac: AC-5
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_validation.py; python -m pytest -q -p no:cacheprovider tests/execution/test_version_history.py; inline record_alternative_choice attacks"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_validation.py; python -m pytest -q -p no:cacheprovider tests/execution/test_version_history.py; inline record_alternative_choice attacks
observed: 17 + 12 passed; before execution -> HistoryEntry, before keeps 23000; after execution -> Version 2 proposed, active stays v1 at 23000; second choice while v2 pending -> VersionError; reconciliation-required refusal tested
attack: second choice while a proposal is pending refused; gate still reads v1 legs after the choice. Residual (deferred issue): an edited alternatives list (99999) is accepted by record_alternative_choice; the gate blocks it before any order

Recorded by the orchestrator from the verifier's returned block.
