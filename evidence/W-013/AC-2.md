---
work_item: W-013
ac: AC-2
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "pytest tests/rules/test_entry.py; stdin script on entry_premium_target and entry_time_window"
---

AC: AC-2
result: pass
commands: pytest tests/rules/test_entry.py; stdin script on entry_premium_target and entry_time_window
observed: ratio spread NET_PREMIUM 1500 from the engine; credit>=1000 TRIGGERED, >=1500 TRIGGERED, >=1500.01 NOT_TRIGGERED; debit -3000 pay<=3000 TRIGGERED, <=2999 NOT_TRIGGERED; time window inclusive
attack: option leg with no LTP -> CANNOT_EVALUATE, not 0; futures-only 0. Round 1 failed here (premium re-implemented without quantity: -40 vs +1500), fixed by engine.net_premium and re-verified.

Recorded by the orchestrator from the verifier's returned block.
