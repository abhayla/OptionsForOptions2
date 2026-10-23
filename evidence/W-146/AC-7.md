---
work_item: W-146
ac: AC-7
requirement: REQ-035
ac_fp: "972f0ffa6c1a"
result: pass
verified_by: "independent verifiers (Opus, fresh context: round 1 on 412b56c6, findings-only round 2 on ce2ab433)"
builder: "builders (earlier work items W-064; row 18 build 94077a89, Sonnet)"
date: '2026-10-24'
commands: "Opus findings-only round 2 on ce2ab433 (fix 94077a89): tests/outcome/test_snapshot_instant.py 5 passed, tests_app/test_outcome_route.py 9 passed, vitest 21 passed"
---

AC: AC-7
result: pass
commands: Opus findings-only round 2 on ce2ab433 (fix 94077a89): tests/outcome/test_snapshot_instant.py 5 passed, tests_app/test_outcome_route.py 9 passed, vitest 21 passed
observed: heading pair from scenario_caption_parts -> serialize scenario_heading -> TableOut -> StrategyTable caption spanning the scenario columns (NIFTY and SENSEX); locked order, % return, breakevens, Greeks and IV shown for everyone
attack: mutants: heading dropped from serialize (killed), caption row removed (killed), colspan off by one (killed); round 1 had FAILED this AC (heading never reached the screen)

Recorded by the orchestrator from the verifier's returned block.
