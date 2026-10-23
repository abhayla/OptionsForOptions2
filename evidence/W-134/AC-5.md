---
work_item: W-134
ac: AC-5
requirement: REQ-048
ac_fp: "e10bd6874b94"
result: fail
verified_by: "independent verifier (Opus, fresh context, round 2 on 06c5c958)"
builder: "builder (Sonnet, builder sequence row 6: build, fix round 1)"
date: '2026-10-22'
commands: "round 2 (Opus) on 06c5c958: attack.py (42 bundle + 12 openapi plants); CI=true pytest tests/test_bundle_secret_scan.py in a clean export; read app-tests.yml and ci.yml"
---

AC: AC-5
result: fail
commands: round 2 (Opus) on 06c5c958: attack.py (42 bundle + 12 openapi plants); CI=true pytest tests/test_bundle_secret_scan.py in a clean export; read app-tests.yml and ci.yml
observed: PARKED (#517). Holds: the real bundle and openapi are clean; vendor hosts are an exact-prefix allow-list; the reply walk is deep; browser-sent eligible/executable/tradable is refused (422) on execute and planned-entry; the scan runs in the frontend job after the build. The round-2 CRITICAL (fail on CI turned the kit's tests job red) is removed in 4cf8f47d (proved on a clean export)
attack: still passing: credential NAMES not on the list (reply token/auth_token/secret/kite_session; bundle enc_token, kite_session, a 'token k:t' header, 'secret:<value>'), bare-IP URLs, Kite prefix traversal, any 8-character execute chunk suffix - the redesign (reply-field inventory) is in #517

Recorded by the orchestrator from the verifier's returned block.
