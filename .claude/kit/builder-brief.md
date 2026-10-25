# Builder brief template

Paste the filled lines INTO the dispatch prompt; do not reference this file (dispatch hooks read the prompt text only).
`Budget:` is read by `agent_budget_required.py` (refused if missing or above the agent's turn share). `Why Opus:` is
read by `agent_model_required.py` (Tier A only). Other lines are read by the checker.

```
Core: <the one mechanism everything else depends on>
Proof: <the smallest real run on real input that shows it works; step 1 of the brief IS this run>
Budget: <N> min wall-clock, <M> tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: <fixes only: the population the defect is a sample of, as a data filter, before and after>
Round: <n>/2
Findings checked: <ids from the findings registry>
Spec quote: <the exact spec line this work implements, with its id>
Threat model: <Tier A guards only: what it must stop, and what it need not>
```

Delete lines that do not apply. Tier C briefs need only `Budget:` and `Report:`.

## Standing items (tick each or say why it does not apply)

- [ ] One test per acceptance criterion; targeted test files only, output to a log file, tail only; a skipped test
  counts as not run.
- [ ] Every test file you changed is run in full, not a name-filtered subset.
- [ ] A feature that decides on another system's answer lists every answer state (stated, absent, not found,
  failed, empty, ambiguous) and what each does.
- [ ] A change to a shown value greps every test tree, end-to-end included, for the old value.
- [ ] Tier A guards only: a mutation test (at most 5 mutants, on a scratch copy) fails when the guard is removed.
- [ ] A guard's known bypasses are written in its README, not chased.

Commit your work in progress in your worktree after each acceptance criterion passes, so a session restart loses at
most one; end the report with the next command to run.
