---
work_item: W-027
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context; round 2 at 7f283fe, regression test checked by orchestrator at efbd56e)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py -k ac5"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py -k ac5
observed: confirm creates v2 with based_on 1; v1 kept unchanged and active until execution; 2 versions
attack: a second proposal while one is pending is refused; a proposal after reconciliation-required is refused; v1 never mutated

Recorded by the orchestrator from the verifier's returned block.
