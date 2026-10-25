---
work_item: W-160
ac: AC-3
requirement: REQ-136
ac_fp: "14c337a739f3"
result: pass
verified_by: "independent checker (Sonnet Tier B diff check on 752c5fef)"
builder: "builder (Sonnet row 32f 6c130473; orchestrator wording fixes c8454fca)"
date: '2026-10-25'
commands: "Read figureDefinitions.js:14-15 against REQ-136 AC-3; Grep of StrategyBuilderPage.vue for ProjectionsNote and the state branches."
---

AC: AC-3
result: pass
commands: Read figureDefinitions.js:14-15 against REQ-136 AC-3; Grep of StrategyBuilderPage.vue for ProjectionsNote and the state branches.
observed: PROJECTIONS_NOTE is word for word the AC-3 text. ProjectionsNote.vue is a plain always-visible <p> (data-testid projections-note), mounted at StrategyBuilderPage.vue:515 directly under <SummaryCards>, inside the branch that shows numbers. It is not inside a hover.
attack: Looked for a state where numbers are shown without the note, and for the note only inside a tooltip. Found neither.

Recorded by the orchestrator from the verifier's returned block.
