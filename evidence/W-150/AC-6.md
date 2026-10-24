---
work_item: W-150
ac: AC-6
requirement: REQ-034
ac_fp: "e856a5470f10"
result: fail
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "tests/scenario/test_modes.py inside the 416 passed"
---

AC: AC-6
result: fail
commands: tests/scenario/test_modes.py inside the 416 passed
observed: At Expiry (default, exact) and Estimated Now (labelled estimate; unavailable with the exact reason without IV) run on build_outcome, the function the outcome route and live push call
attack: (verifier verdict: partial - recorded as fail because the evidence schema has only pass/fail) what-if inputs (target level, target date, IV change) are built by row 37 (W-165, REQ-084) by decision 2026-10-24; not built or checked here

Recorded by the orchestrator from the verifier's returned block.
