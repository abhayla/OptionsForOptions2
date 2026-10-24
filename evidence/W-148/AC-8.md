---
work_item: W-148
ac: AC-8
requirement: REQ-076
ac_fp: "8e405b6fbc73"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes): name and Hedge marks on load via the read control"
---

AC: AC-8
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes): name and Hedge marks on load via the read control
observed: the leg list shows the template the engine matched (Iron Condor with hedge marks [T,F,F,T]; 'Custom Strategy' when none), from the server on load (read control, changes no leg) and after every edit
attack: mutant 'name computed in the browser' killed

Recorded by the orchestrator from the verifier's returned block.
