---
work_item: W-148
ac: AC-1
requirement: REQ-076
ac_fp: "a46e9d226210"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)"
---

AC: AC-1
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)
observed: +/- move an option leg to the next LISTED strike (22800 -> 22850 on the 50 grid, the 100 gap far from ATM followed); refused at the first/last listed strike with the reason; no stepper on a futures leg; an unlisted strike refused, not rounded
attack: mutants 'strike + 50 instead of the listed grid' and 'edge refusal removed' killed

Recorded by the orchestrator from the verifier's returned block.
