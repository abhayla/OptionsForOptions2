---
work_item: W-150
ac: AC-5
requirement: REQ-034
ac_fp: "c0ec179afbc1"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "python probe (build_outcome on the recorded 2026-10-08 frames, narrow config and default); python -m pytest -q -p no:cacheprovider tests/outcome tests/scenario (160 passed) on bf4823e7"
---

AC: AC-5
result: pass
commands: python probe (build_outcome on the recorded 2026-10-08 frames, narrow config and default); python -m pytest -q -p no:cacheprovider tests/outcome tests/scenario (160 passed) on bf4823e7
observed: Narrow long 22400 PE: range 22000..23100, move 330, columns 22300, 22317.25 (ZERO_PNL), 22400, 22500, 22533.25 (CURRENT), 22600 - sorted, unique, every other column a multiple of 100. Long CE (22839.15) and the default wing strangle (two breakevens) likewise.
attack: Narrow config so the expected move widens the range; checked the CURRENT and ZERO_PNL columns exist, are unique and sit between the right grid neighbours. Holds.

Recorded by the orchestrator from the verifier's returned block.
