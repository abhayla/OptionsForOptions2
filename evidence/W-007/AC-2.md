---
work_item: W-007
ac: AC-2
requirement: REQ-017
ac_fp: "a0b37f0a0e1a"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "Read tests/entitlements/test_engine.py; gh run view 36987295445"
---

AC: AC-2
result: pass
commands: Read tests/entitlements/test_engine.py; gh run view 36987295445
observed: CI on head 85fce61 (both success): domain suite run 36987295445 "1597 passed in 22.70s"; App tests run 36987295450 "252 passed, 3 skipped" (skips = parametrized ENDED x non-trial, test_entitlement_store.py:198). Core: caller 2020 recorded_at replaced/refused (log "ledger clock: event_at 2020-01-01 ... outside recorded_at 2026-10-02 09:01:25 +/- 60 seconds (ADR-023 Q256)"); 7 + 30 + 30 history loads under cap 30; post-dated revoke (2106, now+61 s) refused and a real revoke lands; the two-connection test asserts B waited on the per-user lock and the no-lock mutant is caught. Tests not run locally (kit guard blocks the verifier's .claude paths); ac_fp supplied by the orchestrator. Sources exactly {TRIAL, DIRECT_ZERODHA_CUSTOMER, REFERRAL, PAID_MONTHLY, PAID_ANNUAL}; AccessLevel {PRO, LIMITED}; empty ledger LIMITED; each time-limited source PRO on [granted, granted+30d) and LIMITED at the end; Direct customer PRO with no end (2099, expiry None).
attack: Closed enum: an extra or missing source fails set equality. Note: paid month/year durations are passed by the caller; the 365-day year is exercised in test_events.py (1 Oct 2026 + 365 = 1 Oct 2027), not enforced by the engine.

Recorded by the orchestrator from the verifier's returned block.
