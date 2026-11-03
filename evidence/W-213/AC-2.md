---
work_item: W-213
requirement: REQ-169
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "5946f150ca6a"
commands: "read alembic/versions/0034_system_playbook_versions.py; read system_playbook_store.py:101-153; read routes/system_playbooks.py:125-145; vitest system-playbook-admin.test.js (6 pass)"
---
Key attack (overwrite instead of new version) fails: the 0034 guard (:91-94) raises OF034 on any non-INSERT for all roles, plus a BEFORE TRUNCATE trigger; an insert must be max+1 (:96) and restored_from an earlier version (:100); the app role has SELECT and column INSERT only. The reason is required in the store and by a DB CHECK; the audit event is written in the same nested transaction as the INSERT (store:108-114); Restore inserts a new version with restored_from (store:152).

Minor: store:115 reports any IntegrityError (incl. an audit-insert failure) as 'stale'. DB proof owed: tests_app/test_system_playbook_versions.py (core proof, role cannot update/delete/truncate, guard refuses the owner, no-reason refused, stale base refused).

Recorded by the orchestrator from the verifier's returned block.
