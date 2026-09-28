---
work_item: W-018
ac: AC-3
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/marketdata/test_rule_health.py; python -c attacks"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/marketdata/test_rule_health.py; python -c attacks
observed: AllOf/AnyOf behaviour tests pass; build_snapshot derives data_health from the quotes the rule uses, never caller-typed
attack: 3-input rule with a stale non-deciding input -> record shows STALE (worst of used quotes, disclosed not hidden); a quote for an unused contract cannot taint the record

Recorded by the orchestrator from the verifier's returned block.
