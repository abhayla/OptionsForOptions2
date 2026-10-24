---
work_item: W-148
ac: AC-6
requirement: REQ-076
ac_fp: "32655c63ca91"
result: pass
verified_by: "independent verifiers (Sonnet backend check; Sonnet frontend check; Sonnet findings-only round 2 on 48dd0c67)"
builder: "builders (Sonnet: backend 17a9d596..a7b1b4a9; frontend 463dca78, fixes 58b77cd8, 47679238, 48dd0c67)"
date: '2026-10-24'
commands: "Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): spy confirms outcome and margin get only ticked legs; engine: CE wing out UNLIMITED, PE wing out 1,486,322.50 (finite); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)"
---

AC: AC-6
result: pass
commands: Sonnet backend check (verify-row-20b.md; route + domain on the real instrument-list fixture; 9 mutants killed): spy confirms outcome and margin get only ticked legs; engine: CE wing out UNLIMITED, PE wing out 1,486,322.50 (finite); Sonnet frontend check (verify-row-20f.md; vitest mounts of /strategy/builder with leg_edit.py reply shapes)
observed: an unticked leg is left out of summary, payoff, table, margin and Greeks, greyed and labelled 'Left out of the numbers'; every leg unticked shows no zeros (example corrected 0744041e)
attack: mutant 'include ignored in the engine call' killed

Recorded by the orchestrator from the verifier's returned block.
