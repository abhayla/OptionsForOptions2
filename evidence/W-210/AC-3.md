---
work_item: W-210
requirement: REQ-163
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "1aae4254979b"
commands: "read backend/ofo/engine/adjust_history.py; read backend/ofo_app/routes/adjustment_history.py:195-216"
---
The engine handles unconfirmed and failed rows correctly (booked None 'pending', left out of totals and of the position). The route never passes a non-paper fill state (no fill= argument, lines 211-216), so the path is unreachable from any screen; only unit tests exercise it. No imported-real history is wired.

Domain right, wiring missing at adjustment_history.py:211-216. Paper iron condor paths do not hit this case.
