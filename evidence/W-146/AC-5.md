---
work_item: W-146
ac: AC-5
requirement: REQ-035
ac_fp: "ed67ad6cd4ae"
result: pass
verified_by: "independent verifiers (Opus, fresh context: round 1 on 412b56c6, findings-only round 2 on ce2ab433)"
builder: "builders (earlier work items W-064; row 18 build 94077a89, Sonnet)"
date: '2026-10-24'
commands: "Opus check round 1 on 412b56c6 (verify-row-18.md): vitest mount; outcome.py leg_quotes (row 17 fix 90d3a2bc: COMPUTED answers only)"
---

AC: AC-5
result: pass
commands: Opus check round 1 on 412b56c6 (verify-row-18.md): vitest mount; outcome.py leg_quotes (row 17 fix 90d3a2bc: COMPUTED answers only)
observed: Bid/Ask per leg in the Details view for every user from leg_quotes; a missing quote is None (nothing invented); absent when not live
attack: not-live and session-ended answers carry no leg_quotes (row 17 round 2 probe)

Recorded by the orchestrator from the verifier's returned block.
