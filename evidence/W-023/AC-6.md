---
work_item: W-023
ac: AC-6
result: pass
verified_by: "verifier (opus, fresh context, rounds 3-4) and verifier (sonnet, mutation checks W-023e/W-023f)"
builder: "builder (opus); rounds 4-6 tests by builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_no_retry.py tests/execution/test_duplicate_order_guards.py"
---

AC: AC-6
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_no_retry.py tests/execution/test_duplicate_order_guards.py
observed: refused order not retried; no loop or scheduling (AST test); broker reason shown as is; a timeout stays in flight (not Rejected); a definite refusal is mirrored Rejected so the user's next Retry prepares exactly 1 order
attack: M3 (timeout -> Rejected) and M10 (refusal left Submitted) killed; keep-sending-after-refusal mutants killed

Recorded by the orchestrator from the verifier's returned block.
