---
work_item: W-148
ac: AC-5
requirement: REQ-076
ac_fp: "834281c7540d"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): SENSEX lot 20, freeze block per leg; Sonnet findings-only round 2 on 48dd0c67 (AC-5 quantity switch; 4 mutants killed)"
---

AC: AC-5
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): SENSEX lot 20, freeze block per leg; Sonnet findings-only round 2 on 48dd0c67 (AC-5 quantity switch; 4 mutants killed)
observed: lots by default; a Lots/Quantity switch shows each leg's quantity exactly as the server sends it (lots x the instrument file's lot size: 195 NIFTY, 60 SENSEX); above the freeze limit the ADR-092 block reason shows on that leg, never split
attack: mutants 'quantity mode shows lots', 'browser multiplies', 'reply quantity dropped', 'freeze block removed' killed

Recorded by the orchestrator from the verifier's returned block.
