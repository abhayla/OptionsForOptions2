---
work_item: W-005
ac: AC-5
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus), round 3 (fresh builder)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_templates.py; grep for template names in backend *.py; scanner probes"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_templates.py; grep for template names in backend *.py; scanner probes
observed: backend grep: only docstring/comment hits; matching/model/loader are generic (linear solve over data); scan test passes
attack: scanner catches getattr(t,'id')=='iron_condor', a dict keyed by a template id, 'iron'+'_condor', set membership, def price_short_strangle; misses getattr(t,'id')=='x', t['id']=='x', a name split in an f-string (heuristic gaps, none in real code; deferred #10)

Recorded by the orchestrator from the verifier's returned block.
