---
work_item: W-148
ac: AC-9
requirement: REQ-076
ac_fp: "cfb7ab0b479d"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): a 23400 CE changed to a 23200 PE -> no name, no marks, same strikes"
---

AC: AC-9
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): a 23400 CE changed to a 23200 PE -> no name, no marks, same strikes
observed: the shape name is a label only: it never adds, removes, reorders or changes a leg
attack: type change gives Custom Strategy with no hedge marks

Recorded by the orchestrator from the verifier's returned block.
