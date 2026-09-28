---
work_item: W-015
ac: AC-1
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/audit/test_catalogue.py; python -m pytest -q -p no:cacheprovider"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/audit/test_catalogue.py; python -m pytest -q -p no:cacheprovider
observed: 4 passed; full suite 223 passed; the test loads REQ-064 AC-1 from spec/requirements/REQ-064.md on disk, parses 33 phrases and asserts equal sets both ways with the EventType catalogue (all ADR-029 identity events included)
attack: test reads the spec from disk, so a spec edit fails it; missing or extra events fail; slash variants ('started/expired') become two members. Verified after 3 rounds (round 1 AC-2 failed on tail truncation and mutable payloads; round 2 AC-2 failed on a name-based secret guard added by the orchestrator's brief, removed after an independent review; round 3 pass).

Recorded by the orchestrator from the verifier's returned block.
