---
work_item: W-209
requirement: REQ-162
ac: AC-2
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "cfe17f28c7ef"
commands: "read backend/ofo_app/routes/adjustment_opportunities.py:101-104; grep partly_completed backend --include=*.py"
---
The source label and the outcome text are shown, and the paper wording 'Acted on - Paper - not sent to Zerodha' names a state. For an imported real strategy outcome_text (adjustment_opportunities.py:101-104) returns a bare 'Acted on': the Zerodha state (not answered / answer failed) is never named. Nothing in backend/ writes completed or partly_completed (only migration 0031 and the OUTCOMES lists mention them), so no confirmed-fill path exists.

Real-strategy path only; the paper path holds.

Recorded by the orchestrator from the verifier's returned block.
