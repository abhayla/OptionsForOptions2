# Process guards: the per-row review rules enforced by machine (Tier A: a hook changes; size M)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: a builder dispatch whose brief has no numbered attack list is refused by the PreToolUse brief gate.
Proof: step 1 is a failing hook test: a prompt "Your full brief is the file <abs path>/docs/process/builder-sequence-briefs/row-99-x.md"
naming a brief without `Attack list:` is ALLOWED today (the gate matches only `docs/process/brief-*.md` and the
prefixes "Your full brief:" / "Brief:"); after the change it is refused.

Spec basis: none: the spec says nothing about delivery-process guards (searched: attack list, brief gate, row review,
process review in spec/). Owner decisions 2026-10-22 recorded in `docs/process/row-review.md` (rules R1-R5, method)
and the goal contract step 9. Copy from: none - project tooling, no legacy row.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (checked out). Commit as
you go; do NOT push; no PR. Touch ONLY the files below. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\guards`.

## What to build
1. `scripts/hooks/agent_brief_gate.py`: the designated brief is any `.md` under `docs/process/` (subfolders
   included) named after `Your full brief is the file`, `Your full brief:`, `Your brief is the file` or `Brief:`
   (absolute or relative path, either slash). Everything else in its docstring stays (fail open on a missing checker,
   unreadable file, timeout or malformed input).
2. `scripts/orchestrator/check_brief.py`: a BUILDER brief (it has a `Standing items:` line) must also carry
   (a) `Attack list:` followed by at least one numbered item (`1.`), else `MISSING Attack list` (row-review R1);
   (b) a `Budget:` line whose minutes/calls are one of the size pairs 30/40 (S), 60/80 (M or each part of an L), or a
   fix/re-check pair at most half of those (15/20, 20/30, 30/40), else `MISSING size budget` (R3). Verifier and
   measure briefs (no `Standing items:`) are unaffected. Every existing brief under
   `docs/process/builder-sequence-briefs/` must still pass, or report which fails and why.
3. New repo test `tests/test_row_review_log.py` (marked like the other guard tests so `tests/test_*.py` runs it):
   every row of the table in `docs/process/builder-sequence-2026-10-22.md` whose Status starts with `Done` or
   `PARKED` has a heading `### Row N` in `docs/process/row-review.md`; and for every closed row number that is a
   multiple of 3, a heading `### Meta review after row N` exists. It fails closed when either file is missing or the
   table cannot be parsed. Today rows 1-2 are Done and have entries: it passes.

Attack list: (run each before reporting; the Tier A reviewer runs them again)
1. The gate with each prefix form above, absolute and relative paths, backslashes, and a brief in a subfolder ->
   checked; a prompt that only mentions a brief in passing ("for history see docs/process/x.md") -> not checked.
2. A builder brief without `Attack list:`, with `Attack list:` but no numbered item, with `Budget: 45 min, 60 tool
   calls` -> refused; a verifier brief without them -> allowed.
3. The checker crashing, missing, or timing out -> the gate allows (fail open), one stderr line.
4. The row-review test with: a Done row missing its entry; row 3 Done without a meta review; a renamed table file;
   a malformed table row -> red each; today's real files -> green.
5. Every existing brief in `docs/process/builder-sequence-briefs/` and `docs/process/brief-*.md` through the new
   checker: report the list and each result.

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (the new test runs in the existing guard
test set); (c) the gate and the tests fail closed (tests) / open (hook, by its design rule) on shapes they cannot
parse, and name their target by path pattern, not by identifier text; (d) n/a: no other system's answer.
Threat model: in scope - a builder dispatch with an unchecked brief, a closed row with no review entry; out of scope - a
deliberately forged prompt that hides the brief path (the orchestrator writes the prompts).
Findings checked: brief-rule-from-memory, guard-as-forbidden-list
Reviewer checklist: hook tests for every prefix form and both slash styles; the size-pair rule matches row-review R3
exactly; the new repo test is red on each attack case; no existing brief newly refused without a reason; no new
duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated
files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the hook's and the checker's own tests (find them under `tests/`), and `python scripts/ruff_ratchet.py`.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
