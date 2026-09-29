---
work_item: W-023
ac: AC-4
result: pass
verified_by: "verifier (opus, fresh context, rounds 3-4) and verifier (sonnet, mutation checks W-023e/W-023f)"
builder: "builder (opus); rounds 4-6 tests by builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution tests/orders; mutants M1, M2, M3, M6, M10, M13, M16, Own-2, Own-3 (verifier W-023e) and the submit-time block re-check (verifier W-023f)"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution tests/orders; mutants M1, M2, M3, M6, M10, M13, M16, Own-2, Own-3 (verifier W-023e) and the submit-time block re-check (verifier W-023f)
observed: round 3 code: step-0 book sync from the fresh order-status read, registration before send under a client tag, in-flight = non-terminal in the reconciled book, 60 s grace, 5 s skew / 60 s staleness; double Complete on a lagging read -> one order of 65; rejected order no longer locks Complete/Retry/Close; bad broker id after acceptance -> RECONCILIATION_REQUIRED; every listed mutant killed; blocked-after-preparation -> submit refused, 0 orders sent; full suite 979 passed
attack: rounds 1-2 (double order, lockout, untracked accepted order) fixed by a redesign after an independent review; rounds 4-6 were test-only (no production diff) to lock the guards. Surviving informational mutant: Complete orders sells before buys (REQ-056 AC-3 'all buys first is never hard-coded' conflict, owner question)

Recorded by the orchestrator from the verifier's returned block.
