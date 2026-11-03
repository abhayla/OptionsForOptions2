---
work_item: W-214
requirement: REQ-170
ac: AC-3
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "80dbcc0bcd73"
commands: "python -I attack script: ladder (0.30, 0.35), alert_gate.dismiss"
---
Opened at 0.31; a close at 0.36 inside the cool-down opened a second record worse='last'; after dismiss, the same level 0.31 opened nothing and 0.36 opened worse='dismissed'. Cap and quiet-time checks sit after the escalation branch (alert_gate.py:276-285), so they apply to escalations too.

Cap-held escalation after a dismiss read in code only.
