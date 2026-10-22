---
work_item: W-136
ac: AC-3
requirement: REQ-050
ac_fp: "8c4c03418bb8"
result: fail
verified_by: "independent verifier (Opus, fresh context, round 2 on 5a72453d)"
builder: "builder (Sonnet, builder sequence row 8: build, fix round 1, fix round 2)"
date: '2026-10-22'
commands: "round 2 (Opus) on 5a72453d: as AC-1, plus planned-entry and outcome route FeedScope mutations in scratch copies; 72 of 498 selected app tests through the throwaway-database runner (72 passed, stopped at 14% on budget: ~23 s per DB test over the tunnel)"
---

AC: AC-3
result: fail
commands: round 2 (Opus) on 5a72453d: as AC-1, plus planned-entry and outcome route FeedScope mutations in scratch copies; 72 of 498 selected app tests through the throwaway-database runner (72 passed, stopped at 14% on budget: ~23 s per DB test over the tunnel)
observed: PARKED (#519). Every snapshot reader passes feed_scope: outcome.py:448, planned_entry.py:79, tracking.py:120; live push goes through outcome_response; replay contexts have no owner, so nothing is shared there (replay_mode.py:68,194). No lock wait in 5 timeout stack dumps (all idle in selectors.select)
attack: owner dropped from the key -> red; no per-key lock -> red; planned-entry scope None -> red; outcome-route scope None -> red; tracking scope mutation not run (needs the DB); the same 30 surviving key-part mutants as AC-1

Recorded by the orchestrator from the verifier's returned block.
