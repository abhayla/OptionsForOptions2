---
work_item: W-160
ac: AC-4
requirement: REQ-136
ac_fp: "220b471ea966"
result: pass
verified_by: "independent checker (Sonnet Tier B diff check on 752c5fef)"
builder: "builder (Sonnet row 32f 6c130473; orchestrator wording fixes c8454fca)"
date: '2026-10-25'
commands: "Read figureDefinitions.js:8-11 and the model-based entries; tests/figure-definitions.test.js passed (17 tests; it compares MODEL_PHRASE with the engine's model name)."
---

AC: AC-4
result: pass
commands: Read figureDefinitions.js:8-11 and the model-based entries; tests/figure-definitions.test.js passed (17 tests; it compares MODEL_PHRASE with the engine's model name).
observed: breakeven_target (41), estimated_now (90), expected_move_bands (96) and probability_of_profit (101) embed MODEL_PHRASE, which matches the model text in REQ-136 AC-4. max_profit, max_loss and breakeven_expiry append EXACT_AT_EXPIRY. Net premium, charges, reward/risk and the margin figures name no model, which is correct because they are not model-based.
attack: Checked each figure against which kind it is. Looked for a model-based figure that says 'exact' or an exact figure that names a model, and found none. Possible gap: max_profit says 'Exact at expiry' with no mixed-expiry caveat, while max_loss has one. ADR-143 covers loss only, so I did not fail on it.

Recorded by the orchestrator from the verifier's returned block.
