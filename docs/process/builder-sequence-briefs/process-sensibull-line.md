# Process item: check_brief refuses a requirement brief without a Sensibull line (ADR-173)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the new rule before reporting; write the results to a file in your
scratch folder and quote it (R18).
Size: S, 4 files, 4 items
CI: kit tests job (`tests/orchestrator/test_check_brief.py`, `tests/hooks/test_orchestrator_route_hooks.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 12:5x): 30 min / ~120k.

Core: a builder or verifier brief that cites a requirement but says nothing about Sensibull is refused by
`check_brief.py`, so `agent_brief_gate` blocks its dispatch.
Proof: step 1 - run `check_brief.py` on the real brief `docs/process/builder-sequence-briefs/row-12-fix-1.md` (cites
REQ-072, has no Sensibull line): today it exits 0 (red); after the rule it exits non-zero naming the missing line.

Spec basis: ADR-173 decision (2) - check_brief.py refuses every builder and verifier brief without a "Sensibull:" line
that names screen numbers and what is copied, or "Sensibull: none - searched <terms>" when the study has no such screen.
Copy from: none.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`, head 7d93c1bd - its OWN worktree.
Commit with `git commit -F <msg> -- <your paths>`; do NOT push. NEVER stop a process by name; stop only PIDs you
recorded. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\proc-sensibull`.

## What to do
1. `scripts/orchestrator/check_brief.py`: a brief that names any `REQ-###` must carry a line starting `Sensibull:`.
   Accepted forms: (a) it names at least one study screen number (three digits, e.g. `012`, `209-211`) AND a word saying
   what is copied (`copy`, `copies`, `copied`, `same as`); (b) `Sensibull: none - searched <terms>` with at least two
   comma-separated search terms. Anything else (missing line, empty, `n/a`, `none` without terms, screens without what is
   copied) is a miss with a message naming the accepted forms and ADR-173. A brief naming no REQ is exempt (process
   tooling). Reuse the module's existing line-regex style and miss-list plumbing; no new helper copies.
2. `docs/process/builder-brief.md`: add the `Sensibull:` line to the template, right after `Copy from:`, with the two
   forms and one example of each.
3. Fix the red test `tests/hooks/test_orchestrator_route_hooks.py::test_agent_gate_allows_a_builder_brief_with_an_attack_list_and_a_verifier_brief`:
   its sample builder brief predates the mutation-gate rule (and now the Sensibull rule); give the sample the lines
   the rules need. Do not loosen any rule to make it pass.
4. Tests in `tests/orchestrator/test_check_brief.py` for every accepted and refused form below.

Attack list: (each names its test file)
1. REQ brief with no Sensibull line refused; same brief with a valid line passes (`tests/orchestrator/test_check_brief.py`).
2. `Sensibull: none` and `Sensibull: n/a` refused; `Sensibull: none - searched reconnect, stale feed` passes (same file).
3. Screen numbers without a copy word refused; `Sensibull: screens 209-211 - copy the price-changed marker` passes (same file).
4. A process brief naming no REQ passes without the line (same file).
5. The dispatch hook blocks a REQ brief without the line and allows the fixed sample (`tests/hooks/test_orchestrator_route_hooks.py`).
6. Every other existing test in both files still passes; mutants of the new rule all killed (results file quoted).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the rule is a static check of brief text: it fails closed (refuses) on any Sensibull line it cannot classify, and keys on the `Sensibull:` label, not on loose words in the brief; (d) the brief states - REQ named with a valid line, REQ named with no line, REQ named with a malformed line, no REQ named - each tested.
Threat model: in scope - a brief dispatched without the Sensibull study, or with an empty placeholder line; out of scope - a line whose screen numbers are wrong (the verifier checks the copy claim against the study).
Findings checked: guard-as-forbidden-list, brief-rule-from-memory
Reviewer checklist: rule keyed on the label; both forms enforced; exempt only when no REQ is named; hook test fixed
without loosening; gate results quoted; no new duplicated literal; reuse the existing helper; ruff/mypy baselines must
not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
