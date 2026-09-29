---
work_item: W-021
ac: AC-1
result: pass
verified_by: "verifier (opus, fresh context; rounds W-021 to W-021g)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation; scenario scripts (verifiers W-021f, W-021g); coverage mutants"
---

AC: AC-1
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation; scenario scripts (verifiers W-021f, W-021g); coverage mutants
observed: all 7 Q196 triggers map to a run covering every non-exited strategy (PERIODIC fires only when one is active); Monitoring Paused B sharing SELL 23400 CE x50 with active A, broker -100: periodic/after-execution/order-event/reconnect runs give 0 mismatches, nothing blocked, adopt refused; exited id refused as the triggering strategy; 8/8 coverage mutants and the exited-trigger mutant killed
attack: rounds: named-only runs falsely blocked a strategy sharing a contract; a caller map fell back to the named strategy (fail open); periodic compared only active ids. Now coverage is derived from all non-exited records; the trust boundary (caller passes every non-exited record) is documented

Recorded by the orchestrator from the verifier's returned block.
