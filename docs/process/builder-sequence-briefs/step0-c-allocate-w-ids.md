# Step 0 part C: allocate the 63 builder-sequence work items (Tier C bookkeeping)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: one generated set of work-item files passes `python tools/factory_lint.py .` and
`python scripts/orchestrator/coverage.py . --check` with one W-id per table row.
Proof: both commands exit 0 after the files exist, and `python tools/trace_check.py .` reports no new error.

Spec basis: goal contract `docs/process/goal-contract-builder-sequence-2026-10-22.md`, "Step 0": "Allocate all 63
W-ids (one requirement each) and their `coverage-stages.yaml` lines in one commit, so rows never edit that file again
(it changed in 56 of the last 100 PRs)."
Copy from: none - bookkeeping files, no code.
Tier: C.

## Where you work
- Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `docs/builder-feature-reqs` (checked out). Do
  NOT create a branch, commit, push, `git add`, `git stash`, `git checkout` or `git reset`: another agent edits test
  files in the same worktree now. Touch ONLY `work/W-129.md` .. `work/W-191.md`, `docs/process/coverage-stages.yaml`
  and the table file `docs/process/builder-sequence-2026-10-22.md` (add a `W` column only; never change a Status).
- Scratch folder: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\step0c`.
  Write the generator script there (not in the repo).

## What to build
- Row N of the table gets `W-(128+N)`: row 1 = W-129 ... row 63 = W-191. W-129..W-191 are unused on every branch
  (checked 2026-10-22).
- Each file follows the schema the linter enforces (read the work-item schema under the kit's `factory/schemas/` with
  Read, and copy the shape of `work/W-128.md`): `requirement_ids` = the row's ONE requirement; row 17 = REQ-006 (its
  title says REQ-007 is removed in the same row); row 63 has no requirement: if the schema refuses an empty list, give
  row 63 no file and say so in the report. `status: todo`; `tier` = the table's tier (row 63: the highest the schema
  allows for a close-out, or A); `depends_on` = the previous row's W-id (strict order, ADR-168); `title` = the row name
  + the words builder sequence row N in brackets; `objective` = one sentence from the requirement's title; `affected`: `[]` or the
  minimum the schema needs; `tests_required`: the row's ACs, each as `'AC-k: measured at row N'` if the schema accepts
  free text, else the shape it needs (say which); `core`/`proof`: the words set when the row is measured if allowed;
  `next_action: 'Row N: read + measure (builder sequence)'`. Where the row's code already exists on a branch (rows 20,
  30: build/W-126-a1-leg-rows; 26, 36, 37: build/W-127-b2-payoff; 33, 34, 35, 45: PR #509 build/W-124-a3-chain), add a
  body line naming the branch to take code from, hunks for this row only.
- `docs/process/coverage-stages.yaml`: one line per new W-id under the work-items block, in the existing style, stage
  = the requirement's current stage line in the same file, comment `# builder sequence row N: <short name>`.
- Table: add a `W` column after `#`.

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step; (c) n/a: no detector; (d) n/a: no other system.
Reviewer checklist: 63 rows -> 62 or 63 files (row 63 reported); each file links exactly the table's requirement; no
existing W-file changed; no Status changed; lint + coverage pass.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Also run (each bare, from the worktree root): `python tools/factory_lint.py .`, `python tools/trace_check.py .`,
`python scripts/orchestrator/coverage.py . --check`.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table (under 300 words; uncommitted by design).
