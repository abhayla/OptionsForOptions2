---
work_item: W-025
ac: AC-7
result: pass
verified_by: "verifier (sonnet, fresh context; third check at ba980cf)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py -k expected_range"
---

AC: AC-7
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/range/test_pick_lists.py -k expected_range
observed: 4 passed; ExpectedRange is frozen, label fixed to 'user input', any other label and lower > upper refused
attack: constructing with label 'predicted range' is refused; mutation after construction raises

Recorded by the orchestrator from the verifier's returned block.
