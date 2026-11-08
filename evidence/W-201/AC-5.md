---
work_item: W-201
requirement: REQ-112
ac: AC-5
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "a515b5843a88"
commands: "grep -rniE 'why did this trigger' backend frontend/src; sed -n 1,77p backend/ofo/timeline/why.py; sed -n 1,75p frontend/src/pages/AdjustmentOpportunitiesPage.vue"
---
why_did_this_trigger (backend/ofo/timeline/why.py:42) builds from RuleTriggerRecord and FollowUps only, carries no suggestion outcome and has no caller outside ofo/timeline; the phrase appears nowhere in frontend/src. The inbox (AdjustmentOpportunitiesPage.vue:29-38) shows shown_at and outcome_text but not the outcome's time; _record (adjustment_opportunities.py:126) does not expose the timeline. The AC example ('Completed - plan 3 - 11:24') needs the outcome time.

The inbox is the closest view but is not the REQ-040 AC-5 view.

Recorded by the orchestrator from the verifier's returned block.
