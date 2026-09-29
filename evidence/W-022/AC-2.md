---
work_item: W-022
ac: AC-2
result: pass
verified_by: "verifier (opus, fresh context; second check W-022b)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/execution/test_plan.py tests/execution/test_plan_failures.py tests/execution/test_review_summary.py; attack script; mutants M5, M6, M9, M11, M12"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/execution/test_plan.py tests/execution/test_plan_failures.py tests/execution/test_review_summary.py; attack script; mutants M5, M6, M9, M11, M12
observed: sequence built from protection dependencies, margin impact (MarginPlanner: margin with minus without the leg, in-step tie-break; hand-computed condor order (L4,L1,L3,L2) matched) and broker constraints (freeze split 3,000 -> 1,755 + 1,245 with protective slices first; batches of at most 10 never spanning a step); a failing or float-returning planner falls back to protection-only with a stated note
attack: round 1 failed: margin and broker constraints were not inputs (class-3 scope narrowing). Defaults 1,755 / 10 and the margin meaning are labelled unverified (AC-10, ADR-017 Q26). Gap (deferred issue): partial.py Complete uses the protection sequence only, no planner or freeze slices

Recorded by the orchestrator from the verifier's returned block.
