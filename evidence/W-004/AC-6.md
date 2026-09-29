---
work_item: W-004
ac: AC-6
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "same"
---

AC: AC-6
result: pass
commands: same
observed: test_ac6_iv_and_greeks_from_platform_black_scholes uses tolerance 0.00005 against an independent computation; the vendor Greek (-0.9999) is not used as the value
attack: The vendor-Greek-is-reference test would fail if the platform value were replaced by the vendor's; missing IV gives None Greeks with a reason and exact P&L still holds.

Recorded by the orchestrator from the verifier's returned block.
