---
work_item: W-020
ac: AC-3
result: pass
verified_by: "verifier (sonnet, fresh context; AC-3 re-checked at ac72243)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/timeline/test_trigger_record.py; python -c attacks (rec.__class__=Evil, __dict__ injection, object.__setattr__) at ac72243"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/timeline/test_trigger_record.py; python -c attacks (rec.__class__=Evil, __dict__ injection, object.__setattr__) at ac72243
observed: Evil subclass refused (type(strategy) is StrategyRecord; versions read via StrategyRecord.active_version.fget); __class__ reassignment blocked by StrategyRecord.__setattr__; no __dict__ (slots); proposed v2 on an executed strategy records v1; never-executed entry rule records active None / planned 1; exit rule with no active version refused
attack: rounds: a proposed v2 passed as active (fixed), a subclass overriding active_version (fixed). Residual judged out of threat model: object.__setattr__ raw C-level tampering can corrupt the record; no Python code can prevent it and no caller reaches it by mistake

Recorded by the orchestrator from the verifier's returned block.
