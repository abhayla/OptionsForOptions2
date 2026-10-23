---
work_item: W-139
ac: AC-2
requirement: REQ-114
ac_fp: "aa50402d6a9b"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on b04d47f0, round 2 on 0e574b58)"
builder: "builders (Sonnet/Opus, builder sequence row 11: build, fix 1)"
date: '2026-10-23'
commands: "round 2 (Opus, fresh) on 0e574b58: mutation_gate.py mutant A10 (kite_ws._dropped without provider.on_disconnected) on tests_app/test_kite_ws_silence.py"
---

AC: AC-2
result: pass
commands: round 2 (Opus, fresh) on 0e574b58: mutation_gate.py mutant A10 (kite_ws._dropped without provider.on_disconnected) on tests_app/test_kite_ws_silence.py
observed: A10 killed (1 failed, 6 passed), clean run green; 60.0 s close / 59.9 s keep from round 1 (silence.py:94-103)
attack: removed the stale-marking call from _dropped

Recorded by the orchestrator from the verifier's returned block.
