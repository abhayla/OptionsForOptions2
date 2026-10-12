---
work_item: W-070
ac: AC-2
requirement: REQ-065
ac_fp: "d1023ce348f1"
result: fail
verified_by: "verifier (opus, fresh context, 2026-10-12, at af5222c)"
builder: "builder (sonnet; rounds 1-9, 2026-10-11/12)"
date: '2026-10-12'
commands: "python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py; ... tests_app/test_error_boundary.py; python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py; python scripts/orchestrator/db_run.py C:/Abhay/Ventures/OptionsForOptions2-W-070 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py; python probe10.py; python scan10.py; python probe11 driver; python probe9.py; python run9b.py; every_scan replay; python tools/ac_fp.py REQ-065 AC-2 --yaml"
---

AC: AC-2
result: fail
commands: python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_response_door.py; ... tests_app/test_error_boundary.py; python -m pytest -q -p no:cacheprovider tests/test_door_names_private.py; python scripts/orchestrator/db_run.py C:/Abhay/Ventures/OptionsForOptions2-W-070 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_login.py; python probe10.py; python scan10.py; python probe11 driver; python probe9.py; python run9b.py; every_scan replay; python tools/ac_fp.py REQ-065 AC-2 --yaml
observed: 203/21/229/118 passed. N1 302 to https://evil.example/steal?..., N2 302 to https://evil.example/steal, N3 www-authenticate "Basic realm=\"You should buy NIFTY...\"", N5 200 x-evil: unminted with body "You should buy NIFTY, guaranteed"; all CLEAN under every_scan and test_error_boundary_scan.scan. A1-A4 and forger9 flagged.
attack: Pass rule (b) from ADR-003 Q235: a runtime rewrite in a new backend file must be flagged by CI. Plain assignment to door-module constants and helpers (KITE_LOGIN_PAGE, _check_location, WWW_AUTHENTICATE) and seal reuse through the door's public call plus request._send are not flagged, so the AC fails. Normal construction and call paths (the brief's core attacks: outside redirect via location, exception WWW-Authenticate sentence) are refused. Remainder parked in #200.

Recorded by the orchestrator from the verifier's returned block.
