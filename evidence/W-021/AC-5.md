---
work_item: W-021
ac: AC-5
result: pass
verified_by: "verifier (opus, fresh context; rounds W-021 to W-021g)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/reconciliation/test_resolution.py; attack scripts (verifier W-021g); mutants M1-M5"
---

AC: AC-5
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/reconciliation/test_resolution.py; attack scripts (verifier W-021g); mutants M1-M5
observed: every resolution checks its premise against the latest recorded report; exit while the broker holds, stale adopt, other-account report, resolution after a new fill all refused; shared contract (A,B x50) with broker 0 or -50: adopt, prepared closing order and broker-flat exit refused for every holder, both stay blocked, no order proposed; three holders and proposal holders covered; no over-refusal on a separate single-holder contract; mutants killed
attack: verifier W-021g passed the code and failed AC-5 only because the Q198 narrowing for shared contracts was not recorded in the spec; recorded in this PR as Q224 (delegated overnight, ADR-045, reversible) together with Q222, and noted in REQ-060

Recorded by the orchestrator from the verifier's returned block.
