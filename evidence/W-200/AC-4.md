---
work_item: W-200
requirement: REQ-046
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "19a3af3ecdce"
commands: "read backend/ofo/adjustment/approaches.py:376-419 (roll_distance, roll); grep -rn 'Q255|entry distance|entry_spot|spot_at_entry' spec docs backend; read spec/decisions/ADR-239.md and ADR-214.md"
---
The Q255 rule (REQ-046, owner 2026-09-29: keep widths, re-place shorts at their ENTRY distance from spot) is not implemented: roll_distance (approaches.py:376-404) picks the strike by the playbook's target delta, else a 200/500-point fallback; no entry spot or entry distance is stored anywhere in backend/ (0 hits); widths are kept. The REQ-046 example (spot 23,300 + 353 -> 23,650/23,850) cannot be produced. Before/After and the payoff chart (Before dashed) exist.

Owner-level conflict: REQ-046 / Q255 (entry distance) vs the approved playbooks' delta targets (catalogue 2026-10-30, e.g. 'A-02 roll the tested side out to 0.20 delta'; ADR-239). Parked as an owner question 2026-11-04.

Recorded by the orchestrator from the verifier's returned block.
