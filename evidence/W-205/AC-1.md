---
work_item: W-205
requirement: REQ-158
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "e03b84efc49d"
commands: "python -m pytest -q -p no:cacheprovider tests/adjustment/test_system_playbooks_seed.py tests/adjustment/test_playbook_stages.py tests/adjustment/test_playbook_eval.py tests/adjustment/test_registry.py; python json load backend/ofo/adjustment/system_playbooks.json; read backend/ofo/adjustment/playbook_types.py"
---
143 passed. The seed has exactly 12 system rows (strangle, straddle, ic, ifly, credit, debit, longopt, longvol, calendar, ratio, dirfly, other), no intraday PB-02 type; TYPE_KEYS is pinned to the catalogue labels at import; the editor lists types from GET /playbooks/types.

DB proof owed: tests_app/test_adjustment_check.py::test_seed_twelve_system_rows_ic_approved_t19_one_rest_draft_every_body_valid.

Recorded by the orchestrator from the verifier's returned block.
