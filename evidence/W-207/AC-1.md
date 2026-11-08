---
work_item: W-207
requirement: REQ-160
ac: AC-1
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10)"
date: 2026-11-03
ac_fp: "0da8e71c8157"
commands: "read frontend/src/lib/playbookEditor.js:6-93; read frontend/src/pages/AdjustmentsPage.vue:48-171"
---
STEPS holds the 7 steps in order (Expiry and stages, When to look, Approaches to show, Days and dates, Situations, Limits and guards, Test on my strategies); the 'This playbook in plain words' aside is computed from the live working copy, so it changes as values change. Attack: labels not loaded -> empty summary, no crash.

Code read only; frontend/tests/adjustments-page.test.js not run.

Recorded by the orchestrator from the verifier's returned block.
