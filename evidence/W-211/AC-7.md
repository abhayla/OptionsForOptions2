---
work_item: W-211
requirement: REQ-167
ac: AC-7
result: pass
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 4)"
date: 2026-11-04
ac_fp: "7a9b74da4605"
commands: "read backend/ofo/settings/registry.json:605-625; read frontend/src/lib/legEdit.js:28, OptionChainPage.vue:36,125-133, SaveDraftBar.vue:95,178, StrategyBuilderPage.vue:533, stores/settingsValues.js:15-50; grep 8000|10000|UNDO_MS frontend/src; cd frontend && npx vitest run tests/settings-values.test.js; python -m pytest -q -p no:cacheprovider tests/test_settings_literal_guard.py; cd frontend && npx vitest run tests/option-chain.test.js -t ndo"
---
Registry other.undo_one_leg_seconds default '8' (1-120) and other.undo_clear_all_seconds default '10', citing REQ-167 AC-7 / F-79 / Q-SET-1. OptionChainPage.vue:128 limits.millis(UNDO_SECONDS_KEY) feeds setTimeout; Clear all uses waitMs(CLEAR_UNDO_SECONDS_KEY) (StrategyBuilderPage.vue:533, SaveDraftBar.vue:178); a null read offers no Undo, never a typed time; no 8000/10000 undo literal left. settings-values 5/5, literal guard 12/12, option-chain no-literal test pass. Attack: no leftover hard-coded undo time found.

Q-SET-1 is open at docs/process/owner-questions-2026-10-31.md:67 (not in spec/open-questions.md); F-79 at spec/findings.md:1122.

Recorded by the orchestrator from the verifier's returned block.
