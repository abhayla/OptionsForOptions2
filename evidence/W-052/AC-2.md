---
work_item: W-052
ac: AC-2
requirement: REQ-064
ac_fp: "c860d867c666"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "python tools/ac_fp.py REQ-064 AC-2 --yaml; gh run view 36976900800 --log (grep passed/skipped/ERROR); gh run view 36976900787 --log (grep passed); git show 1a9771d:tests_app/test_audit_store.py; git show 1a9771d:backend/ofo_app/alembic/versions/0002_audit_store.py (grants, triggers, TRUNCATE)"
---

AC: AC-2
result: pass
commands: as above
observed: App tests run 36976900800 "137 passed in 5.76s", no skip/xfail; domain suite run 36976900787 "1413 passed", kit_selftest passed. Server log refusals: payload outside allowlist; "event type order_submitted has no payload allowlist (REQ-063 AC-5)"; "hash is not the SHA-256 of the canonical text"; "canonical text does not match the row's columns"; "does not extend the anchor"; permission denied for audit_events and audit_anchor; must be owner of audit_events; allowlist mutation refusals. Core proof test: 3 events (first with Decimal 1365.00 and a datetime) appended as the app role, reloaded on a fresh connection (NullPool), verify().ok, hashes and events equal, price is Decimal with str "1365.00", stored form {"$decimal":"1365.00"}. Owner byte change on payload/actor/timestamp/hash/previous_hash (non-tail row) raises AuditChainError seq=<row>. Tail delete by the owner detected via the anchor. Concurrency: B blocked while A holds the lock; afterwards seq and previous_hash link, verify ok. App role refused UPDATE/DELETE on events, UPDATE/DELETE/INSERT on the anchor, DISABLE TRIGGER. Allowlist raw-insert cases (7) refused; undeclared type writes no row, anchor unchanged; bogus hash "e"*64 refused; six canonical mismatches refused.
attack: Vacuous pass from skips - none (137 passed, refusals in the server log). Decimal scale drift - asserted as the string "1365.00". App-role paths to remove/alter events - UPDATE, DELETE, TRUNCATE, TRIGGER, REFERENCES not granted; trigger functions SECURITY DEFINER with EXECUTE revoked. Tail truncation - anchor (count, last_hash) not writable by the app role. Minor gap: TRUNCATE by the app role covered by the allowlist privilege check, no behavioural test. DB tests read from CI, not re-run locally (no PostgreSQL on the laptop).

Recorded by the orchestrator from the verifier's returned block.
