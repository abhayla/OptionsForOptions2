---
work_item: W-026
ac: AC-3
result: pass
verified_by: "verifier (opus, fresh context; round 3 W-026c against the independent review's bar)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "sink battery via private names (to prove the sink's own checks only); FINNIFTY twin catalogue; mutants M1-M4, M7, M11, M12, M14, M16"
---

AC: AC-3
result: pass
commands: sink battery via private names (to prove the sink's own checks only); FINNIFTY twin catalogue; mutants M1-M4, M7, M11, M12, M14, M16
observed: symbol mismatch, BANKNIFTY, wrong side, over-quantity, a 2x65 split, unknown strategy, another strategy's order, another version, re-selling a filled leg, closing an unheld leg, closing more than held, a bad choice, a leg-name alias and a forged request are all refused at the sink with 0 transport calls
attack: survivors M7 (underlying filter), M14 (sink room across split orders) and M15 (binding check) are backup checks proven by direct attack but not pinned by tests (deferred issue). Price is passed through unchecked; price protection is REQ-056 AC-7 (later item)

Recorded by the orchestrator from the verifier's returned block.
