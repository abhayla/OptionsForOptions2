---
work_item: W-007
ac: AC-1
requirement: REQ-017
ac_fp: "ab7a897757b4"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "Read tests/entitlements/test_engine.py; test_mutations.py names; gh run view 36987295445"
---

AC: AC-1
result: pass
commands: Read tests/entitlements/test_engine.py; test_mutations.py names; gh run view 36987295445
observed: CI on head 85fce61 (both success): domain suite run 36987295445 "1597 passed in 22.70s"; App tests run 36987295450 "252 passed, 3 skipped" (skips = parametrized ENDED x non-trial, test_entitlement_store.py:198). Core: caller 2020 recorded_at replaced/refused (log "ledger clock: event_at 2020-01-01 ... outside recorded_at 2026-10-02 09:01:25 +/- 60 seconds (ADR-023 Q256)"); 7 + 30 + 30 history loads under cap 30; post-dated revoke (2106, now+61 s) refused and a real revoke lands; the two-connection test asserts B waited on the per-user lock and the no-lock mutant is caught. Tests not run locally (kit guard blocks the verifier's .claude paths); ac_fp supplied by the orchestrator. test_trial_boundaries_seven_days_from_registration: registration 29 Sep 10:15:30 IST, expiry 6 Oct 10:15:30, LIMITED at start-1us, PRO at start and end-1us, LIMITED at end; test_no_boolean_free_or_paid_field_and_access_is_recomputed_from_events walks 9 record types (no bool / free / paid / is_pro / premium field beyond three pinned names) and shows access changes with events; test_naive_query_time_is_refused.
attack: Boundary mutants exist (end made inclusive, start made exclusive; names read). Weak point: the name check is a word list, but the bool-type check would catch a renamed flag.

Recorded by the orchestrator from the verifier's returned block.
