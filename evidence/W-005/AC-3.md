---
work_item: W-005
ac: AC-3
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus), round 3 (fresh builder)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_templates.py; python - (YAML attack script)"
---

AC: AC-3
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_templates.py; python - (YAML attack script)
observed: 27 passed; 21 templates load; a template added only as data loads, resolves, prices and matches back; iron condor core 23000/23100/23300/23400, max profit 3000, max loss 4500
attack: duplicate keys (flow map, template, inner map, alias as key), merge keys, !!python tags, empty/null templates, billion-laughs aliases: all refused; 150 templates load in 0.65 s and a shared shape is caught. Outside AC (deferred #10): a unicode-hyphen OTM claim, 'limited risk' on a naked call, a put-OTM claim backed only by a call sign all load.

Recorded by the orchestrator from the verifier's returned block.
