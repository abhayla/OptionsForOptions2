---
work_item: W-207
requirement: REQ-160
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "a2dee644dfa7"
commands: "read frontend/src/pages/AdjustmentsPage.vue:253-299; read backend/ofo_app/routes/playbooks.py:299-304"
---
pickPlaybook -> openPicked -> GET /playbooks/:id returns the full body (for a system playbook its current version's body); show() clones it into saved and work, which the steps and summary bind to; same for system and own playbooks. Attack: a failed read closes the editor and shows the server sentence instead of half-filled values.

Code read only.
