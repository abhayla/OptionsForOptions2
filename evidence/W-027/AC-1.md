---
work_item: W-027
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context; round 2 at 7f283fe, regression test checked by orchestrator at efbd56e)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py -k ac1; attack script (REMOVE/RESIZE unknown slot, ADD on held slot, remove all legs)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_modification.py -k ac1; attack script (REMOVE/RESIZE unknown slot, ADD on held slot, remove all legs)
observed: apply_changes raises ModificationError for REMOVE/RESIZE on a slot the active version never held, ADD on an occupied slot and removing every leg; the roll returns one StrategyDefinition with the 4 expected slots
attack: a new leg (22,900 PE) is only ever merged into the StrategyDefinition via dataclasses.replace, never returned as a standalone leg

Recorded by the orchestrator from the verifier's returned block.
