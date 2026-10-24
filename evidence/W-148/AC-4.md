---
work_item: W-148
ac: AC-4
requirement: REQ-076
ac_fp: "6afc6bd1a091"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): multiplier 1 -> 65/leg, 3 -> 195/leg, max loss 7085.00 -> 21255.00; Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)"
---

AC: AC-4
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): multiplier 1 -> 65/leg, 3 -> 195/leg, max loss 7085.00 -> 21255.00; Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)
observed: a strategy multiplier 1-50 (a fixed select) sets lots to base lots x multiplier; 1 restores base lots; 0, 51, 2.5 and '3' refused (422)
attack: mutant 'multiplier upper bound 51' killed

Recorded by the orchestrator from the verifier's returned block.
