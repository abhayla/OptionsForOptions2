---
work_item: W-144
ac: AC-2
requirement: REQ-038
ac_fp: "02b6e7472201"
result: pass
verified_by: "independent verifiers (Opus, fresh context; round 1 on d99b2097, round 2 on 735ba1a6; DB part CI #525 on f5a1059c)"
builder: "builders (Opus, builder sequence row 16: build, fix 1)"
date: '2026-10-23'
commands: "round 1 (Opus) on d99b2097 found the in-flight gap; fix 1 (9698f26d..735ba1a6); round 2 (Opus, fresh) on 735ba1a6; DB: local 168 passed (test_strategy_versions_app, test_strategy_store, test_strategy_followups) + CI #525 api job on f5a1059c (pass)"
---

AC: AC-2
result: pass
commands: round 1 (Opus) on d99b2097 found the in-flight gap; fix 1 (9698f26d..735ba1a6); round 2 (Opus, fresh) on 735ba1a6; DB: local 168 passed (test_strategy_versions_app, test_strategy_store, test_strategy_followups) + CI #525 api job on f5a1059c (pass)
observed: after a fill, update goes to _propose and version 1 stays active; restore refused; edits serialized by the FOR UPDATE row lock, the PK (strategy_id, number) and the one-proposed unique index; an open plan is IN_FLIGHT before the versions check (strategy_store.py:389-393)
attack: fail closed on an unreadable store (UNREADABLE) and an open plan (IN_FLIGHT), also after versions exist

Recorded by the orchestrator from the verifier's returned block.
