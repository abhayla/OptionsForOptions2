---
work_item: W-020
ac: AC-4
result: pass
verified_by: "verifier (sonnet, fresh context; AC-3 re-checked at ac72243)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/timeline/test_trigger_record.py; attack scripts"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/timeline/test_trigger_record.py; attack scripts
observed: follow-up kinds parsed from the AC-4 list on disk; follow-up for an unknown seq or a non-trigger entry refused; a broker report containing advice words is printed verbatim as quoted data
attack: duplicate kind refused; verify() rejects a follow-up whose trigger_seq is not an earlier trigger

Recorded by the orchestrator from the verifier's returned block.
