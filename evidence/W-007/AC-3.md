---
work_item: W-007
ac: AC-3
requirement: REQ-017
ac_fp: "9896bf8fc567"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "Read tests/entitlements/test_events.py; grep tests_app/test_entitlement_store.py; gh run view 36987295450"
---

AC: AC-3
result: pass
commands: Read tests/entitlements/test_events.py; grep tests_app/test_entitlement_store.py; gh run view 36987295450
observed: CI on head 85fce61 (both success): domain suite run 36987295445 "1597 passed in 22.70s"; App tests run 36987295450 "252 passed, 3 skipped" (skips = parametrized ENDED x non-trial, test_entitlement_store.py:198). Core: caller 2020 recorded_at replaced/refused (log "ledger clock: event_at 2020-01-01 ... outside recorded_at 2026-10-02 09:01:25 +/- 60 seconds (ADR-023 Q256)"); 7 + 30 + 30 history loads under cap 30; post-dated revoke (2106, now+61 s) refused and a real revoke lands; the two-connection test asserts B waited on the per-user lock and the no-lock mutant is caught. Tests not run locally (kit guard blocks the verifier's .claude paths); ac_fp supplied by the orchestrator. test_entitlement_stores_source_start_expiry_status_reference_and_audit: source, granted_at, duration, reference, Audit(actor, recorded stamped by the ledger clock), frozen; start 1 Oct 2026, expiry 1 Oct 2027, ACTIVE; 11 invalid grant variants refused; only Direct customer is open-ended; AuditNote carries no recorded_at.
attack: A caller recorded_at is refused at the type level (TypeError), in the store before SQL, and by the database (2020 refusal in the log).

Recorded by the orchestrator from the verifier's returned block.
