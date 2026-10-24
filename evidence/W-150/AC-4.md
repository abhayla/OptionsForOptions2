---
work_item: W-150
ac: AC-4
requirement: REQ-034
ac_fp: "f7ae0c3e72c1"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "probe.py (verify-22-r2); 12 sed mutants; pytest tests/outcome/test_expected_move_range.py"
---

AC: AC-4
result: pass
commands: probe.py (verify-22-r2); 12 sed mutants; pytest tests/outcome/test_expected_move_range.py
observed: recorded 2026-10-08 frames: forward 22529.17, ATM 22550, CE mid 124.28 IV 0.124691, PE mid 145.55 IV 0.125116, mean 0.1249035, 5 days, move 329.41 -> 330 (REQ-027 Q254 formula, REQ-106 AC-1 ATM IV); narrow config long 22400 PE 22100..22800 -> 22000..23100; tie at 22525 -> 22500; UNHEALTHY/UNAVAILABLE/missing side -> no move
attack: nearest-leg IV, ATM at spot, CE only, PE only, move dropped, farthest expiry, one-sided move, LTP basis, UTC days, no 1-day floor all KILLED; tie_upper and stale_refused SURVIVED (MINOR, behaviour correct by probe, deferred to #532)

Recorded by the orchestrator from the verifier's returned block.
