---
work_item: W-150
ac: AC-2
requirement: REQ-034
ac_fp: "c05d9828f850"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "python -m pytest -q -p no:cacheprovider tests/outcome tests/scenario tests/marketdata (416 passed) on f5ab7f1e"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/outcome tests/scenario tests/marketdata (416 passed) on f5ab7f1e
observed: test_core_expected_move_is_the_atm_iv_move asserts ls.current == 22533.25 with the move applied
attack: a wider move-driven range (22000..23100) still contains the current level; 11 of 13 mutants killed

Recorded by the orchestrator from the verifier's returned block.
