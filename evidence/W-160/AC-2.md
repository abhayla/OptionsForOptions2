---
work_item: W-160
ac: AC-2
requirement: REQ-136
ac_fp: "e1a2cc010244"
result: pass
verified_by: "independent checker (Sonnet Tier B diff check on 752c5fef)"
builder: "builder (Sonnet row 32f 6c130473; orchestrator wording fixes c8454fca)"
date: '2026-10-25'
commands: "Read frontend/src/lib/figureDefinitions.js 1-107; tests/figure-definitions.test.js passed (17 tests); Grep ADR-003.md for the banned words."
---

AC: AC-2
result: pass
commands: Read frontend/src/lib/figureDefinitions.js 1-107; tests/figure-definitions.test.js passed (17 tests); Grep ADR-003.md for the banned words.
observed: One catalogue (figureDefinitions.js) read by FigureHint.vue and ProjectionsNote.vue, with a wording test over every text. No banned word in any text. funds_needed (line 74) says buy legs are placed before sell legs. max_loss (line 29) says no single maximum is shown on different expiries and cites ADR-143. I saw the pre-fix text, where max-profit repeated its phrase and charges said 'brokerage, exchange fees and taxes'. The coordinator says PR #547 fixed both; I did not re-read it.
attack: Looked for advice, prediction or odd wording in each of the 15 texts and found none that advises. Checked the charges sentence against REQ-081 and ADR-082's itemised list (brokerage, STT, exchange transaction charges, SEBI, stamp duty, GST); it was a loose summary, not a mismatch, and is now reported fixed.

Recorded by the orchestrator from the verifier's returned block.
