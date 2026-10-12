---
work_item: W-069
ac: AC-2
requirement: REQ-065
ac_fp: "d1023ce348f1"
result: fail
verified_by: "verifier (opus, fresh context, 2026-10-12, re-check at af5222c)"
builder: "builder (sonnet; round 1 + fix rounds pricing-scan and Tier A, 2026-10-11)"
date: '2026-10-12'
commands: "Re-check of W-069 AC-2 on the W-070 head af5222c (same REQ-065 AC-2, same door): python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py; ... tests_app/test_error_boundary.py; python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py; db_run.py ... tests_app/test_kite_login.py; probe10/probe11 drivers"
---

AC: AC-2
result: fail
commands: Re-check of W-069 AC-2 on the W-070 head af5222c (same REQ-065 AC-2, same door): python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py; ... tests_app/test_error_boundary.py; python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py; db_run.py ... tests_app/test_kite_login.py; probe10/probe11 drivers
observed: 203/21/229/118 passed. N3 puts advice text in a 401 error's www-authenticate header and N5 puts free text on the wire (200, body "You should buy NIFTY, guaranteed"); neither is flagged by any CI scan. The earlier PASS (sonnet verifier, 2026-10-11, at 28a8f0d) is withdrawn: Opus verifiers on 2026-10-11/12 also forged bodies through bytes.__new__, copyreg, pickle and ctypes on the W-069 door (closed by W-070 rounds 5-7).
attack: Pass rule (b) from ADR-003 Q235 applied to W-069's core claim that only emit writes a body: module rebinding and seal reuse from a new backend file are not flagged by CI. Remainder parked in #200; W-069's door is superseded by W-070's (merged PARTIAL).

Recorded by the orchestrator from the verifier's returned block.
