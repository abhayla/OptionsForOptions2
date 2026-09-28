---
work_item: W-012
ac: AC-4
result: pass
verified_by: "verifier (Opus 5.5, fresh context)"
builder: "builder (opus)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (sequences A/B/C, reconcile attacks, flat case)"
---

AC: AC-4
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_versions.py; python - (sequences A/B/C, reconcile attacks, flat case)
observed: overfill then FAILED -> flag set; PARTIAL then REJECTED -> flag set; wrong resolution refused; empty actor refused; reconcile audited (actor, reason, RECONCILED outcome, time, reference); second reconcile refused
attack: Own random sequences (1,500, flat positions, side flips, overfills, unasked futures): invariant never broken. Verified after 3 rounds + independent review (round 1 trusted the broker's status word; round 2 cleared mismatches across a sequence). Known gap (deferred issue, REQ-060): a flat broker position cannot be reconciled, so the strategy stays blocked — the broker state is recorded and wins and execution is blocked per ADR-018, so AC-4 holds.

Recorded by the orchestrator from the verifier's returned block.
