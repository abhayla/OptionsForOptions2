---
work_item: W-020
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context; AC-3 re-checked at ac72243)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/timeline; attack scripts (7717c98, ac72243)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/timeline; attack scripts (7717c98, ac72243)
observed: no edit/delete API; Timeline __setattr__/__delattr__ raise; entries() returns a tuple copy; a changed stored value is caught by verify (first_broken_index=1)
attack: setattr, delattr, nested detail mutation, internal list reassignment: all refused; a last-entry forgery or truncation is detected when the head anchor is supplied (same design as the audit log)

Recorded by the orchestrator from the verifier's returned block.
