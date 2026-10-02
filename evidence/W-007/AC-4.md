---
work_item: W-007
ac: AC-4
requirement: REQ-017
ac_fp: "f7d8cddb1794"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "Read tests/entitlements/test_engine.py; grep test_mutations.py; gh run view 36987295445 and 36987295450"
---

AC: AC-4
result: pass
commands: Read tests/entitlements/test_engine.py; grep test_mutations.py; gh run view 36987295445 and 36987295450
observed: CI on head 85fce61 (both success): domain suite run 36987295445 "1597 passed in 22.70s"; App tests run 36987295450 "252 passed, 3 skipped" (skips = parametrized ENDED x non-trial, test_entitlement_store.py:198). Core: caller 2020 recorded_at replaced/refused (log "ledger clock: event_at 2020-01-01 ... outside recorded_at 2026-10-02 09:01:25 +/- 60 seconds (ADR-023 Q256)"); 7 + 30 + 30 history loads under cap 30; post-dated revoke (2106, now+61 s) refused and a real revoke lands; the two-connection test asserts B waited on the per-user lock and the no-lock mutant is caught. Tests not run locally (kit guard blocks the verifier's .claude paths); ac_fp supplied by the orchestrator. test_stacked_referral_real_example_pro_until_10_oct_plus_referral_on_20_sep_is_9_nov: referral segment 10 Oct - 9 Nov 2026, PRO at 9 Nov-1us, LIMITED at 9 Nov; ADR-023 rules 2, 3 and 5 covered (paid during trial starts at trial end; banked referral days; paid revoke pulls referral forward, event list grows, nothing deleted); audit payloads inside the allowlist; paid revoke audited as ENTITLEMENT_CHANGED; append order enforced.
attack: Mutants for stacking removed, sequencing fixed at natural end, revocation ignored exist (names read); concurrency covered by the waited-asserting lock test and its mutant.

Recorded by the orchestrator from the verifier's returned block.
