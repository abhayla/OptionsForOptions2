---
work_item: W-020
ac: AC-5
result: pass
verified_by: "verifier (sonnet, fresh context; AC-3 re-checked at ac72243)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/timeline/test_why.py; python -c why_did_this_trigger on the stressed golden condor and on a never-executed entry"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/timeline/test_why.py; python -c why_did_this_trigger on the stressed golden condor and on a never-executed entry
observed: answer quotes rule, exact live P&L -3450.00 vs threshold -3000 (hand-computed -3450.00), timestamp, source, data health, 'Active strategy version: 1.' / 'none (not yet executed); evaluated against planned version 1.'
attack: 'you should' injected into a platform template raises ValueError at runtime; every number in the answer traces to the record

Recorded by the orchestrator from the verifier's returned block.
