---
work_item: W-214
requirement: REQ-170
ac: AC-2
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "0bb95b2e272e"
commands: "python -I attack script (alert_gate.step); python -m pytest -q -p no:cacheprovider tests/adjustment/test_alert_gate.py tests/adjustment/test_alert_gate_lapse_restore.py"
---
Band = rearm_fraction x |threshold| (alert_gate.py:189-196). T-07 at 80, intraday: a close of 72 lapses, 75 does not; a re-open after 72 once the 5 min cool-down passed gave a new record; cleared inside the cool-down gave nothing; cool-down passed but only back to 75 gave nothing.

Weekly/monthly margins read from registry defaults only.
