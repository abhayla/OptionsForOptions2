---
work_item: W-146
ac: AC-8
requirement: REQ-035
ac_fp: "1d28e06c4ec2"
result: pass
verified_by: "independent verifiers (Opus, fresh context: round 1 on 412b56c6, findings-only round 2 on ce2ab433)"
builder: "builders (earlier work items W-064; row 18 build 94077a89, Sonnet)"
date: '2026-10-24'
commands: "Opus check round 1 on 412b56c6 (verify-row-18.md): catalogue_picker.py:84-85 + snapshot.py:118 refusal; tests/outcome test_expired_leg_is_refused; CI App tests (DB suites + Playwright e2e) green on 412b56c6: tests_app/test_catalogue_picker_api.py"
---

AC: AC-8
result: pass
commands: Opus check round 1 on 412b56c6 (verify-row-18.md): catalogue_picker.py:84-85 + snapshot.py:118 refusal; tests/outcome test_expired_leg_is_refused; CI App tests (DB suites + Playwright e2e) green on 412b56c6: tests_app/test_catalogue_picker_api.py
observed: the picker offers only listed, not-expired contracts of the underlying (SQL filter expiry >= today); an expired id posted to the outcome route is refused
attack: the expiry-day-after-15:30 offer is a MINOR in #532

Recorded by the orchestrator from the verifier's returned block.
