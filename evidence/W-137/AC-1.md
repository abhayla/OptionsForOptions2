---
work_item: W-137
ac: AC-1
requirement: REQ-113
ac_fp: "9cfdf3c3b1cd"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round (Opus) on 4b829faf (code 8ff10625): throwaway-DB run of 44 tests_app files (1088 passed, 1 flake fixed after); mutant M16; earlier rounds on A0 (2) and A1+C"
---

AC: AC-1
result: pass
commands: final round (Opus) on 4b829faf (code 8ff10625): throwaway-DB run of 44 tests_app files (1088 passed, 1 flake fixed after); mutant M16; earlier rounds on A0 (2) and A1+C
observed: price socket part: the API in bus mode opens no Kite websocket (test_feed_process_boundary.py:78); the market-data process owns every user's socket and idles with no session (feed_main.py:385). Order-update stream part deferred (order path, REQ-060)
attack: no-session start exits instead of idling -> killed; API opening its own socket in bus mode -> killed (A0 rounds)

Recorded by the orchestrator from the verifier's returned block.
