# Builder brief template

Copy the lines below into the dispatch prompt and fill them in. Paste the filled lines INTO the prompt; do not
reference this file. The dispatch hooks read the prompt text only, and a line that lives in a file is invisible to them.

Which hook reads which line (checked against `.claude/hooks/`):

| Line | Read by |
|---|---|
| `Budget: <N> min wall-clock, <M> tool calls` | `agent_budget_required.py` (refuses a prompt with no Budget line, or one above its share of the agent's turn limit) |
| `Why Opus:` and the reason line the routing table names for its top escalation model (only when the dispatch needs them) | `agent_model_required.py` (the `model` field is set on every dispatch; those models need a reason line of 12+ characters) |
| `Spec quote:` / `Spec basis:` | no dispatch hook reads them today; `spec_basis_gate.py` reads `Spec basis:` in owner questions, not briefs |
| `Report: evidence-table` and every other line | no hook; the reviewer reads them |

## Fill-in lines, in this order

```
Core: <the one mechanism everything else depends on>
Proof: <the smallest real run on real input that shows it works; step 1 of the brief IS this run>
Budget: <N> min wall-clock, <M> tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words)
Class: <fixes only: the population the defect is a sample of, as a data filter, before and after>
Proof: <fixes only: the one real-data run that shows the class is fixed>
Threat model: in scope <...> / out of scope <...>   (any guard or check: what it must stop, and what it need not)
Round: <n>/2
Findings checked: <ids from the findings registry this change was checked against>
Attack list: <the attacks the final verifier will run, one per line; written by the start check or the measure step before the build, never by the builder>
Guard tests: <the repo's guard test files the change must keep green>
Precondition: each "merged"/"exists"/"done" claim in this brief checked against GitHub: <how, and the result>
Spec quote: <the exact spec line this work implements, with its id>
Spec quote: <one line per requirement or decision the work touches>
```

Delete the lines that do not apply (the `Class:` pair for new work; the threat model for work that adds no guard).
`Core:` and `Proof:` stay for new work; a fix keeps `Class:` and its own `Proof:`.

## Standing items (tick each or say why it does not apply)

- [ ] A new pass inside a time-budgeted job reuses the job's existing small reservation, never the whole remaining
  budget, and a test shows the higher-priority work still runs.
- [ ] A CI step that gains a non-builtin import runs after the dependency install step.
- [ ] A static detector fails closed on shapes it cannot resolve (re-exports, renamed exports, same-named local
  functions) and names its guard by import source, not identifier text.
- [ ] A feature that decides on another system's answer lists every answer state (stated, absent, not found,
  failed, empty, ambiguous) and what each does.
- [ ] A change to a shown value greps every test tree, end-to-end tests included, for the old value.
- [ ] After merging main, re-run the lint ratchet.
- [ ] One test per acceptance criterion; targeted test files only, output to a log file, tail only.
- [ ] Every guard has a mutation test that fails when the guard is removed.
- [ ] Where a detector keeps losing, the brief asks for a structural guarantee (the one path every case passes) and
  checks that path really runs first.
- [ ] The builder runs each listed attack and reports its result before reporting done.
- [ ] Run every test file you changed in full, never a name-filtered subset, before reporting done.
- [ ] A skipped test counts as not run and is reported as skipped.
- [ ] A mutation check edits a scratch copy, never a checked-out file.
