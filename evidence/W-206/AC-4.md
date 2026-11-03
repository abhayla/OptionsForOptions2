---
work_item: W-206
requirement: REQ-159
ac: AC-4
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "4f0dfa7f6658"
commands: "read playbook_eval.py lines 660-960; read adjustment_check.py lines 140-153 and 296-312; read background.py lines 962-1066"
---
The iron condor's on-rules act in the worker: expiry + action 5 (close_if_short_within_pct 0.3 from 14:30) via _expiry_close; beforeWeekend/beforeHoliday + action 0 (from 15:00) via _carry_check with NSE calendar days; the tick key includes the IST minute so clock rules fire without a price change. But day_answers (playbook_eval.py ~797-810) handles only those two combinations and _tighten (adjustment_check.py:145) handles expiry + percent: kinds weekday, afterBreak, beforeExpiry, monthlyWeek, dom, date, event, away and actions 1, 2, 3, 6 are stored and shown but never act, with no 'not checked' label.

The iron condor's own off rules are inert by design. Worker DB tests not run.

Recorded by the orchestrator from the verifier's returned block.
