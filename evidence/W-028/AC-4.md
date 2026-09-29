---
work_item: W-028
ac: AC-4
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_complete_slices.py; python -m pytest -q -p no:cacheprovider; attack script on the real instrument fixture; 17 source mutants"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_complete_slices.py; python -m pytest -q -p no:cacheprovider; attack script on the real instrument fixture; 17 source mutants
observed: 38 passed; 1209 passed; send_guard.py unchanged; hand-computed slices 650@260=[260,260,130], 390@260=[260,130], 650@65=10x65, 585@300=[260,260,65], 650@325=[325,325]; freeze below one lot refused; SENSEX lot 20 from the catalogue: 100@50=[40,40,20], 30 refused; a refused 2nd protective slice sends 2 CE slices and withholds the dependent sell, slice 1 stays SUBMITTED; a timeout leaves both slices SUBMITTED ('outcome unknown'); Complete/Retry while slices are in flight prepare nothing; a concurrent second preparation is refused
attack: 14 of 16 mutants caught; M15 cannot change behaviour; M11 not applied. Close Partial does not slice: not required by AC-4's text ('Before completing ... submits only the required order(s)'); belongs to REQ-056 AC-10 (deferred issue)

Recorded by the orchestrator from the verifier's returned block.
