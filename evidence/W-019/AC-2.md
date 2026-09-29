---
work_item: W-019
ac: AC-2
result: pass
verified_by: "verifier (opus, fresh context; round 3 after independent review)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/orders/test_no_state_before_fill.py; python -m pytest -q -p no:cacheprovider tests/orders/test_ledger_property.py; attack script"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/orders/test_no_state_before_fill.py; python -m pytest -q -p no:cacheprovider tests/orders/test_ledger_property.py; attack script
observed: 23 + 5 passed; submitted order position 0, after a 10-unit fill Executed/10/pos 10; identical replay keeps 1 ledger row; replay with different qty/contract/side/price -> FillConflictError; unknown order / wrong contract / wrong side / over-quantity refused; trade id T1 reused on another order fills under its own key; 1000 fills 0.073s; reconcile equal ok, higher blocks that strategy only, lower raises
attack: rounds 1-2 reds all refused or no-op; key lookup before validation judged safe (a new key always runs full order validation). Residuals (deferred issue): a lower broker count raises but does not block submit (core invariant 6 / ADR-018); a trade id with trailing space is a second key

Recorded by the orchestrator from the verifier's returned block.
