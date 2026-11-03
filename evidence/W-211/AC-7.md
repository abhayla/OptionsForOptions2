---
work_item: W-211
requirement: REQ-167
ac: AC-7
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 2)"
date: 2026-11-03
ac_fp: "7a9b74da4605"
commands: "grep undo_one_leg_seconds|undo_clear_all_seconds frontend/src backend; grep F-79|Q-SET-1 spec"
---
Not verified in budget. Seen: registry keys at backend/ofo/settings/registry.json:605,617; reads at frontend/src/lib/legEdit.js:28 and frontend/src/pages/OptionChainPage.vue:36; F-79 at spec/findings.md:1122. Not seen: defaults 8 and 10, the reads reaching the timers, Q-SET-1 open status.

Remaining: registry defaults, timer use, spec/open-questions.md Q-SET-1.

Recorded by the orchestrator from the verifier's returned block.
