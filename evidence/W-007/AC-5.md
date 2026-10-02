---
work_item: W-007
ac: AC-5
requirement: REQ-017
ac_fp: "2d570d3a9d98"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus)"
date: '2026-10-02'
commands: "Read tests/entitlements/test_independence.py; gh run view 36987295445"
---

AC: AC-5
result: pass
commands: Read tests/entitlements/test_independence.py; gh run view 36987295445
observed: CI on head 85fce61 (both success): domain suite run 36987295445 "1597 passed in 22.70s"; App tests run 36987295450 "252 passed, 3 skipped" (skips = parametrized ENDED x non-trial, test_entitlement_store.py:198). Core: caller 2020 recorded_at replaced/refused (log "ledger clock: event_at 2020-01-01 ... outside recorded_at 2026-10-02 09:01:25 +/- 60 seconds (ADR-023 Q256)"); 7 + 30 + 30 history loads under cap 30; post-dated revoke (2106, now+61 s) refused and a real revoke lands; the two-connection test asserts B waited on the per-user lock and the no-lock mutant is caught. Tests not run locally (kit guard blocks the verifier's .claude paths); ac_fp supplied by the orchestrator. AST import scan: ofo/entitlements imports only stdlib and itself, with a discriminating test on 5 forbidden synthetic imports; access_at signature is exactly [ledger, at]; no public engine parameter named strategy/broker/session/zerodha/kite/identity/email/connected.
attack: Weakness: the scenario proof is structural (the engine cannot see strategy or broker state), which is what the AC requires; the scanner cannot silently pass (its own test discriminates).

Recorded by the orchestrator from the verifier's returned block.
