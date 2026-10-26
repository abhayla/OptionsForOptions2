---
work_item: W-153
requirement: REQ-055
ac: AC-3
result: fail
verified_by: "independent verifier (Opus row 25 check, round 1 at dd488f49 and round 2 at 85a70222, PR #574)"
builder: "builders (Sonnet row 25 eab9d6b8, fix 69d7bdc0; orchestrator lint/schema/test-wording commits)"
date: 2026-10-26
ac_fp: "c798814d614e"
commands: "python vr2-attr.py (recorded reply); grep Zerodha says|Margin (Zerodha) in backend/ofo/errors frontend/src"
---
round 1 MAJOR fixed: Zerodha's own figure 6409.00 and our ADR-094 estimate 13474.50 are now labelled apart in every text
round 2 MINOR open: the Execute refusal's second sentence 'Zerodha would reject these orders for insufficient margin' (backend/ofo/errors/templates.py:945) states our estimate's verdict as Zerodha's

Shipped under ADR-189 (MINOR after round 2); tracked in issue #537 F2.

Recorded by the orchestrator from the verifier's returned block.
