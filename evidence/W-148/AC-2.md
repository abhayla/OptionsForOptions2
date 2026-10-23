---
work_item: W-148
ac: AC-2
requirement: REQ-076
ac_fp: "0e7a6c833066"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes): Save Draft after a step posts the new contract id"
---

AC: AC-2
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes): Save Draft after a step posts the new contract id
observed: a stepped leg re-captures its planned entry (45.00 at 09:21:28) while the others keep 09:20:00; no price -> planned_entry null; the reply carries the new contract id and lot size so the stepped contract is saved
attack: step then Save Draft: never the old id, never none

Recorded by the orchestrator from the verifier's returned block.
