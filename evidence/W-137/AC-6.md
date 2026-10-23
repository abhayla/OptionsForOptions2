---
work_item: W-137
ac: AC-6
requirement: REQ-113
ac_fp: "92f6dad142f7"
result: pass
verified_by: "independent verifiers (Opus, fresh context; final round on 4b829faf)"
builder: "builders (Sonnet, builder sequence row 9: parts A0, A1, B, C and their fix/finish rounds)"
date: '2026-10-23'
commands: "final round: mutants M02-M06, M11, M12"
---

AC: AC-6
result: pass
commands: final round: mutants M02-M06, M11, M12
observed: one registry with each cap's source and date (order_limits_registry.py:47-55, F-57, F-59, ADR-170); beyond 3000 instruments refused and logged, never truncated (kite_ws.py:176-196); a 4th socket on one key refused and logged, the user's status says capped and the broker page shows it
attack: truncate / no log / no per-key cap / off-by-one / cap ignoring the key / capped not read / capped not published -> all killed

Recorded by the orchestrator from the verifier's returned block.
