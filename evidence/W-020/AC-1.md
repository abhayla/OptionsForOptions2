---
work_item: W-020
ac: AC-1
result: pass
verified_by: "verifier (sonnet, fresh context; AC-3 re-checked at ac72243)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/timeline (at 7717c98 and again at ac72243; diff between them touches only records.py and test_trigger_record.py)"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/timeline (at 7717c98 and again at ac72243; diff between them touches only records.py and test_trigger_record.py)
observed: 25 then 26 passed; AC-1 entry types parsed from spec/requirements/REQ-040.md on disk equal the EntryType enum; an older entry is refused as non-chronological
attack: backdated EXIT refused; a follow-up 1s before its trigger refused; enum checked against the spec file on disk, not a copy

Recorded by the orchestrator from the verifier's returned block.
