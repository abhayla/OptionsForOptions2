---
work_item: W-026
ac: AC-5
result: pass
verified_by: "verifier (opus, fresh context; round 3 W-026c against the independent review's bar)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_strategy_guard.py; independent recompute; mutants M9, M15"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_strategy_guard.py; independent recompute; mutants M9, M15
observed: removing the 23,600 CE: max loss 8,175 -> UNLIMITED at lot 75 (7,085 -> UNLIMITED at lot 65), breakevens (22909, 23491) -> (22865, 23535), message 'This action changes your strategy's risk profile'; identical legs not flagged; margin change and unknown margin flagged; forged, missing and reused tokens refused
attack: acknowledgement-bypass mutant killed; the binding-mismatch line (M15) is reachable only through private names and has no pinning test (deferred)

Recorded by the orchestrator from the verifier's returned block.
