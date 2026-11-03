---
work_item: W-207
requirement: REQ-160
ac: AC-3
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "7c7dee8fa001"
commands: "read routes/playbooks.py:395-541; read adjustment_check.py:126-155,387-427; read AdjustmentsPage.vue:140-160, playbookEditor.js:136; npx vitest run tests/adjustments-page.test.js"
---
Holds: Test runs the unsaved body, rolls back and records nothing; a Not-checked row carries its reason; the no-strategy text is 'No current {type} strategy to test against'; rows show strategy, value and threshold. Fails the AC's example form: a row is a 5-column table ('Would flag | Short delta at or above | 0.41037 | 0.35'), not 'spot 23,380 within 0.3% of 23,450 CE (rule 0.5%)' - no strike or spot level shown; routes/playbooks.py:~527 calls result_out(r, None), so the server's condition line falls back to the trigger id.

The letter (strategy, value, threshold) holds; the example wording does not.

Recorded by the orchestrator from the verifier's returned block.
