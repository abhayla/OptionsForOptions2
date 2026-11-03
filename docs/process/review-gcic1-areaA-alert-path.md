# Review brief: GC-IC1 Tier A, area A - the alert path (day rules, carry check, situations, worker gate, T-13 / T-16)

Reviewer: fresh context, read-only (no file writes in any repo; scratch only under your own scratchpad). Run the attacks FIRST, read after. Findings + failing inputs, no code.
Range: feature/adjustments 37824fb9..<head given in the dispatch>, these merges only: step 1a/1b/1c (day rules, carry check), 5a (#638/#639, stage-change re-level ADR-237 (8)), 5b (T-13 day open from index day values, T-16 worker margin cache), 6a (S-02 / S-12), the rule-id fix (day.* / sit.*).
Spec: REQ-159 AC-4 / AC-5, REQ-165, REQ-170, ADR-235, ADR-237 incl. (8), ADR-240.
Budget: 20 min wall-clock, 40 tool calls.

Attacks (each: run it, then verdict with the failing input or "held"):
1. Mutants on a scratch checkout (max 5): carry check fires at 14:59; a stage change without re-level opens nothing; S-12 fires on day 2; T-13 uses yesterday's day_open; the worker margin read every cycle. Each must turn an existing test red.
2. Any rule id the evaluator can produce outside `[A-Za-z0-9_.-]{1,64}` (run the guard test; try a body with an odd `when` value).
3. Screen vs worker parity for the day rules and S-02 (same inputs, same readings): read `state_of` / `state_from_market`.
4. A record opened outside `alert_gate.step` (grep every `open_suggestion` caller).
5. Restart: a stored record with an old colon-form id - restore without crash, never re-opened as a new rule.
Report: evidence-table (claim | command + result), findings ranked CRITICAL / MAJOR / MINOR with file:line and a failing input, "covers the class: yes / no" per finding. Under 400 words.
