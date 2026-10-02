---
work_item: W-051
ac: AC-2
requirement: REQ-064
ac_fp: "c860d867c666"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "git diff origin/main...bd95e32 --stat; git show bd95e32:work/W-051.md, backend/ofo_app/alembic/versions/0001_baseline_ledger_clock.py, tests_app/test_ledger_clock.py, tests_app/conftest.py, backend/ofo_app/ledger.py; Grep AC-2 in spec/requirements/REQ-064.md; gh run view 36973761266 --log (job api); gh run view 36973761266 --json headSha,conclusion; gh pr checks 102; gh run view 36973761271 --log"
---

AC: AC-2
result: pass
commands: as above
observed: CI run 36973761266 (job api, headSha bd95e322, conclusion success), step "Run app tests (database tests as ofo_app)" with OFO_REQUIRE_DB_TESTS=1 and both database URLs set: "39 passed in 0.97s", none skipped or failed (conftest fails rather than skips when the URL is missing under that flag). lint-and-test run 36973761271: "1413 passed", smoke passed, kit_selftest passed. Server log: (b) "ledger clock: event_at ... is outside recorded_at ... +/- 60 seconds (ADR-023 Q256)" for +/-2 min, +/-65 s and NULL; (c) "permission denied for table ledger_entries" for UPDATE, DELETE, TRUNCATE and an INSERT naming id; (d) "must be owner of table ledger_entries" for DISABLE TRIGGER name/ALL and "must be owner of relation" for DROP TRIGGER; session_replication_role and temporary tables refused; allowlist refusals for database owner, CREATE on public, TEMPORARY, membership. (a) check_caller_recorded_at_is_ignored passes 2020-01-01 and asserts the stored value lies between DB clock reads before and after. Grants: SELECT, column INSERT (kind, event_at, recorded_at, payload), sequence USAGE; PUBLIC revoked; allowlist runs before and after grants. Expected values from the spec text (60 s window, 2 min refused, 30 s accepted).
attack: Silent skip in CI - not possible (flag fails, log 39 passed 0 skipped). Vacuous mutation tests - each runs as owner in a rolled-back transaction, SET LOCAL ROLE to the app role, and requires AssertionError with a specific message (trigger dropped -> "caller's recorded_at was stored"; GRANT UPDATE/DELETE -> "not refused"; app role as table owner -> DISABLE TRIGGER "not refused"); a final test confirms the real guard is intact. Other write paths: ON CONFLICT DO UPDATE and SELECT FOR UPDATE need UPDATE (not granted); TRUNCATE, replica role, temp-table shadow, id choice, membership, database ownership, schema CREATE, TEMPORARY all covered. Minor gaps, not failing: exact +/-60 s boundary untested (55/65 s used); only ledger_entries exists, so AC-2 for audit/timeline tables depends on later items reusing this base; 39 counted from the CI total only. Proof read from CI, not re-run locally (no PostgreSQL on the laptop).

Recorded by the orchestrator from the verifier's returned block.
