---
work_item: W-127
ac: AC-4
requirement: REQ-084
ac_fp: "cc1d71067bc4"
result: pass
verified_by: "independent Tier A verifier (Opus, fresh context)"
builder: "builder (Sonnet, lane B cluster B2)"
date: '2026-10-22'
commands: "verifier independent Black-Scholes script vs ofo.engine.model.estimate; verified sha 25e33c3af33b62622d2fa5ac060d1513ee8bee65"
---

AC: AC-4
result: pass
commands: verifier independent Black-Scholes script vs ofo.engine.model.estimate; verified sha 25e33c3af33b62622d2fa5ac060d1513ee8bee65
observed: 22,800/23,000 bull call spread, level 23,000, target 25 Oct 15:30 IST, IV +2.0: marks 237.69/99.22, P&L -114.75 both; long-leg delta 0.7950866530 both
attack: independent pricer (r 6.5%, T 2/365, IVs 15%/14%), not the test's

Recorded by the orchestrator from the verifier's returned block.
