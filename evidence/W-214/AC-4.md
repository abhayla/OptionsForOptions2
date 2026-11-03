---
work_item: W-214
requirement: REQ-170
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "5b0d7d9e0a7d"
commands: "grep -rn 'HELD_TEXT_IDS|alert_held|held_daily_limit|held_quiet' backend frontend/src (excluding explanations.py)"
---
The only hit outside explanations.py is the definition at backend/ofo/adjustment/alert_gate.py:31-33 (HELD_TEXT_IDS); no route and no frontend file reads HELD_TEXT_IDS or the alert_held_* ids, so nothing renders 'held: daily limit' / 'held: quiet time' in the strategy timeline, while AC-4 says a held crossing is shown, never dropped silently. Gate logic itself (6 opened, 2 held) taken from round 1.

Literal-id grep; a consumer building the id dynamically could be missed - confirm by reading the timeline route and component.

Recorded by the orchestrator from the verifier's returned block.
