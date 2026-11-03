---
work_item: W-201
requirement: REQ-112
ac: AC-4
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "97531c83e95f"
commands: "read backend/ofo_app/alembic/versions/0031_adjustment_playbooks.py:234-272; read playbook_store.py _CLOSE_SUGGESTION (:233-240); read routes/adjustment_opportunities.py inbox_body"
---
The close UPDATE appends one timeline entry with outcome and suggestion_id, only WHERE outcome='open'. The DB guard allows only open->dismissed|acted_on|lapsed and acted_on->completed|partly_completed, requires exactly one appended entry per change, keeps the timeline append-only and forbids DELETE. A second close gives suggestion_not_open (409). Attack: a double write is refused in code and in the guard.

Later migrations (0036+) not re-read for guard changes. DB proof owed: tests_app/test_playbook_store.py, tests_app/test_adjustment_opportunities.py.
