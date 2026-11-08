---
work_item: W-206
requirement: REQ-159
ac: AC-2
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "9d5ac8682eb5"
commands: "python -I snippet listing triggers and data/greyed of tests/fixtures/adjust_scenarios/_playbooks.json and the ic body in backend/ofo/adjustment/system_playbooks.json; read playbook_eval.py:223-232,529-545; read AdjustmentsPage.vue:76-92; grep T-17|T-10c across spec, backend, fixtures"
---
(1) The data state shows only when t.greyed is set (AdjustmentsPage.vue:82-84): T-11b has data='vix' with greyed None in all 12 playbooks and T-20 'user', so neither shows 'later (India VIX)'; no trigger shows 'available'; only T-11c and T-20b show 'Needs price history (not in V1)'. (2) The ic body's 27 triggers have no T-17 event trigger and no T-10c, so 'needs the admin event list' appears nowhere. Non-firing works: data != ok gives NotChecked data_unavailable (playbook_eval.py:540), with a generic text.

No spec text defers T-17 or T-10c (grep found nothing). The '9 variants' count not reconciled with the catalogue (8 plus T-20b).

Recorded by the orchestrator from the verifier's returned block.
