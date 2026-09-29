---
work_item: W-027
ac: AC-4
result: pass
verified_by: "verifier (sonnet, fresh context; round 2 at 7f283fe, regression test checked by orchestrator at efbd56e)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py (at 7f283fe, then 13 passed at efbd56e); mutations: skip the gate call, drop the strategy_id/active-legs grounding"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py (at 7f283fe, then 13 passed at efbd56e); mutations: skip the gate call, drop the strategy_id/active-legs grounding
observed: no public function takes a SafetyResult; the single check_pre_execution call is inside prepare_confirmed_modification; skip-the-gate mutation turns 3 tests red; forged self-consistent active_legs/hash with pro_entitled=False is blocked ENTITLEMENT_REQUIRED by the real code; the grounding mutation, which left the suite green at 7f283fe, turns the 2 regression tests added at efbd56e red
attack: round 1 failed: a hand-built passing SafetyResult activated v2 (now structurally impossible). Round 2 attacks: context naming another strategy is overwritten; a result for another version raises; gate block leaves v1 active; gate called exactly once (spy). Scope note: futures legs raise ModificationError (not required by REQ-037's AC text)

Recorded by the orchestrator from the verifier's returned block.
