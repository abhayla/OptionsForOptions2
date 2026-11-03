---
work_item: W-206
requirement: REQ-159
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "f1be64b02405"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment (723 passed); python -I snippet importing backend/ofo/adjustment/playbook_stages.check_stages; read backend/ofo/errors/templates.py:1287-1293, frontend/src/lib/playbookEditor.js:37-52, AdjustmentsPage.vue:68-74"
---
Default weekly 5+/2-4/0-1 and monthly 10+/3-9/0-2 pass check_stages. Overlap refused: 'Days 2 to 4 are in both Last and Near (weekly expiries)'; gap refused: 'Days 2 to 2 are in no stage'; missing days 0-1 refused; save routes call check_stages (playbooks.py:194); the editor's add/remove keep trigger values in step and Remove is disabled below 2 stages. Attack: a bounded stage past the open end 366 is accepted (harmless).

Stage order in the refusal follows start day ('Last and Near', not the example's 'Near and Last'); same content. Vitest not run.

Recorded by the orchestrator from the verifier's returned block.
