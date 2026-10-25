---
work_item: W-160
ac: AC-1
requirement: REQ-136
ac_fp: "4894945cd02f"
result: fail
verified_by: "independent checker (Sonnet Tier B diff check on 752c5fef)"
builder: "builder (Sonnet row 32f 6c130473; orchestrator wording fixes c8454fca)"
date: '2026-10-25'
commands: "npx vitest run tests/figure-definitions.test.js tests/strategy-builder-hints.test.js -> 2 files, 35 passed; npx vitest run (16 files importing SummaryCards/MarginLine/PopFigure/ScenarioControls/StrategyBuilderPage) -> 16 files, 297 passed; Grep of frontend/src for net_premium/charges/funds_needed/expected_move/breakeven_target -> only figureDefinitions.js, plus ExecuteCost.vue:13 (Net premium, no mark). All run at worktree head 752c5fef (pre-fix), not re-run on c8454fca."
---

AC: AC-1
result: fail
commands: npx vitest run tests/figure-definitions.test.js tests/strategy-builder-hints.test.js -> 2 files, 35 passed; npx vitest run (16 files importing SummaryCards/MarginLine/PopFigure/ScenarioControls/StrategyBuilderPage) -> 16 files, 297 passed; Grep of frontend/src for net_premium/charges/funds_needed/expected_move/breakeven_target -> only figureDefinitions.js, plus ExecuteCost.vue:13 (Net premium, no mark). All run at worktree head 752c5fef (pre-fix), not re-run on c8454fca.
observed: All 15 figures have a catalogue entry (figureDefinitions.js:20-105). Marks are wired for: max profit, max loss, breakeven (at expiry), reward/risk, time value, intrinsic value (SummaryCards.vue), margin needed + margin available (MarginLine.vue, checked branch only), estimated-now (ScenarioControls.vue), probability of profit (PopFigure.vue, when switched on). MISSING a mark because no builder screen shows the figure yet: net premium (the only place it shows, ExecuteCost.vue:13, has no mark), charges, funds needed, breakeven on the target date, expected-move bands. The row that renders each of these is not known to me.
attack: Looked for every AC-1 figure on a screen with no mark, and for a mark on a figure the screen does not show (the finding browser-infers-a-server-permission). Found the first kind (5 figures), not the second. Hover, focus, tap and Escape are handled in FigureHint.vue:19-46; I read the code and did not exercise it in a browser.

Recorded by the orchestrator from the verifier's returned block.
