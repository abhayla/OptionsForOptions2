---
work_item: W-148
ac: AC-7
requirement: REQ-076
ac_fp: "42dbf7dbef80"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): save and Execute models refuse 'included'; Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)"
---

AC: AC-7
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): save and Execute models refuse 'included'; Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)
observed: Execute refused while any leg is unticked with the exact text; the tick never reaches the saved definition or the execution plan
attack: mutants 'tick written into the saved definition' and 'tick added to the save body' killed

Recorded by the orchestrator from the verifier's returned block.
