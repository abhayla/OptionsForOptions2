---
work_item: W-202
requirement: REQ-155
ac: AC-1
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "8f516d8a4ae8"
commands: "python -c (APPROACH_IDS against A-01,A-02,A-04,A-05,A-06,A-11,A-24..A-31,A-36); grep -c A-30 backend/ofo/adjustment/system_playbooks.json"
---
APPROACH_IDS (approaches.py:93) builds A-01, A-02, A-04, A-05, A-06, A-11, A-24..A-29, A-31, A-35, A-36: A-30 (add lots to the tested side) is missing while the AC names 'A-24 to A-31'. A-30 is switched off in every system playbook (12 occurrences in system_playbooks.json), so the iron condor system path never asks for it, but a user copy that switches it on would get no builder.

Spec/code mismatch: drop A-30 from the AC (SPEC CHANGE) or build it. Not verified in budget: the adjustment.py:369-377 ValueError attack (entry price with more than 2 decimals).

Recorded by the orchestrator from the verifier's returned block.
