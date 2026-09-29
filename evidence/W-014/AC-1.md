---
work_item: W-014
ac: AC-1
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_safety_checks.py; inline attack scripts over check_pre_execution"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_safety_checks.py; inline attack scripts over check_pre_execution
observed: 167 passed; entry-all-flipped blocked with MARKET_CLOSED,VERSION_NOT_EXECUTABLE,BROKER_NOT_CONNECTED,SESSION_INVALID,RULES_INVALID,DEPENDENCIES_UNSATISFIED,MARGIN_INSUFFICIENT,RECONCILIATION_MISMATCH; exits skip margin/eligibility/rule validity; exit-stale-data asks confirmation; recon None blocks entry and exit; recon on S-9 does not block S-1; wing-only close -26,000.00 -> -2,990,000.00 needs Pro; whole put spread allowed; calendar rules per spec; futures entry unknown -> Pro
attack: naked short / over-close / flip / new contract labelled EXIT -> EXIT_NOT_REDUCE_ONLY; inflated legs, foreign hash, wrong version id, missing hash -> ACTIVE_LEGS_UNVERIFIED; omitting reconciliation -> TypeError; margin short by 1 paisa blocks, equal passes. Residual (deferred issue): made-up legs with a self-computed hash pass; the hash is a consistency tie, integration must source legs from the store

Recorded by the orchestrator from the verifier's returned block.
