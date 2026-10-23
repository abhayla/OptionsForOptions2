# Process item: the reference-product difference register and its gates (ADR-176)

Common brief: docs/process/builder-brief.md (Budget hard stop: at 72 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on every new check before reporting; write the results to a file in your
scratch folder and quote it (R18).
Size: M, 9 files, 7 items
CI: kit tests job (`tests/orchestrator/test_reference_register.py` (new), `tests/test_reference_register_real.py` (new),
`tests/orchestrator/test_check_brief.py`, `tests/hooks/test_orchestrator_route_hooks.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 13:5x): 60 min / ~300k.

Core: a record file in the register folder is validated by one command, and a row whose requirement has an open COPY
record cannot close: `reference_register.py --close-check REQ-135` exits 1 naming the record.
Proof: step 1 - put ONE real record (REQ-135, expiry shown as "27 Oct (6 Days)" vs our option chain's raw date, from
the row 5 study gap G-05-1, builder row of REQ-135) in the chosen folder; prove that `python tools/factory_lint.py
<worktree>`, `python tools/check_spec_refs.py <worktree>` and `python scripts/orchestrator/regen.py <worktree>` still
pass with it there (they scan `spec/`); then `--check` passes it, `--close-check REQ-135` exits 1 naming it, and
flipping it to `verified` exits 0.

Spec basis: ADR-176 decision (1) every difference "is one record in its own file", kind COPY, DIFFERENT-BY-DECISION,
NO-SCREEN or MATCH; (2) the brief, verify and close gates and the CI failures it lists; (3) public
repo limits; (4) the label is "Reference:" and new text never names the reference product; (5) always copy, bugs never,
approved extras through one batched SPEC CHANGE list. ADR-173 (2) the brief line.
Copy from: none.
Reference: none - searched register, difference record, brief label (delivery tooling; no product screen).

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`, head 729039c8 - its OWN worktree.
Commit with `git commit -F <msg> -- <your paths>`; do NOT push. NEVER stop a process by name; stop only PIDs you
recorded. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\proc-register`.
NAME RULE (ADR-176 (4)): never write the reference product's name in any file you create or change (code, tests,
comments, messages, commit text). The name ban check below compares a hash, so the name never appears in code.

## What to do
1. Records: one JSON file per difference, `RD-NNN.json`, in `spec/reference-diffs/` (preferred: it sits with the
   requirements it changes). If step 1 shows a kit tool rejects that folder, use `docs/reference-diffs/` and say why.
   Fields: `id`, `kind` (COPY | DIFFERENT-BY-DECISION | NO-SCREEN | MATCH), `title`, `reference_behaviour` (own words,
   at most 400 characters), `reference_screens` (list, e.g. "screen 012", "catalogue 097"), `reference_label`
   (optional, at most 40 characters: the one short quoted label), `ours` (what we do, file:line or REQ AC), `req`
   (REQ-###), `ac` (optional AC-n), `row` (builder row number), `status` (open | built | verified | deferred |
   decided), `adr` (required for DIFFERENT-BY-DECISION), `issue` (required for deferred), `spec_change` (bool: our
   extra written in an approved AC that copying would remove - goes on the owner's batched list), `bug` (bool: the
   reference behaviour is a measured bug; `ours` then describes its nearest working behaviour), `recorded` (date).
2. `scripts/orchestrator/reference_register.py`:
   - `--check`: every field and enum; id unique and equal to the file name; `req` exists in spec/requirements; `adr`
     exists in spec/decisions; `row` exists in `docs/process/builder-sequence-2026-10-22.md` AND that row's REQ cell
     names `req` (rows like "REQ-006 + REQ-007" count both); length limits; no record text whose lower-cased words
     include a word with sha256 `51eb0a649e8ea998a8e8527a47858a91d20b263772281af86fffa67f898ca33a` (the name ban);
     the generated page is current.
   - `--open REQ-### ...`: prints the ids of every blocking record of those requirements (blocking = kind COPY or
     `spec_change` true, status not in verified / deferred / decided).
   - `--close-check REQ-### ...`: exit 1 naming each blocking record, else exit 0.
   - `--render`: writes `docs/process/reference-differences.md`: sections in this order - SPEC CHANGE batch for the
     owner (open `spec_change` records), NO-SCREEN capture list, COPY by builder row with status, DIFFERENT-BY-DECISION
     with ADR, MATCH count; a header line with the record count per kind. Deterministic (sorted, no clock).
3. `scripts/orchestrator/check_brief.py`: rename the `Sensibull:` label to `Reference:` (ADR-176 (4)) in the rule,
   messages, template text and tests; ADD: for every REQ the brief names, every id `--open` returns for it must appear
   in the brief's `Reference:` line (a brief may not drop an open record). Keep the two accepted forms for a REQ with no
   records. Rename `process-sensibull-line.md` to `process-reference-line.md` with `git mv` and reword it per the name
   rule.
4. `docs/process/builder-brief.md`: the `Reference:` line (forms, the open-record rule, one example each).
5. Tests: `tests/orchestrator/test_reference_register.py` (unit, temp folders: each field miss, each enum, missing ADR,
   missing REQ, row whose REQ cell does not name the req, length limits, the name ban, close-check blocking and not,
   render order and determinism); `tests/test_reference_register_real.py` runs `--check` over the real folder (so CI
   fails a bad record or a stale page).
6. Hook sample in `tests/hooks/test_orchestrator_route_hooks.py` follows the label rename; no rule loosened.
7. Commit the one real record from step 1 and the rendered page.

Attack list: (each names its test file)
1. A DIFFERENT-BY-DECISION record without `adr`, or with an ADR that does not exist, fails `--check` (`tests/orchestrator/test_reference_register.py`).
2. A COPY record whose `row` belongs to another requirement fails (same file).
3. A record holding the banned name in any field, any case, fails; the name never appears in the test source (built from bytes at run time) (same file).
4. `--close-check` exits 1 for an open COPY or open spec_change record and 0 once it is verified, deferred with an issue, or decided (same file).
5. A brief naming REQ-135 whose `Reference:` line omits an open record id is refused by check_brief (`tests/orchestrator/test_check_brief.py`).
6. The old `Sensibull:` label no longer satisfies the rule; `Reference:` does (same file).
7. The real folder passes `--check` and the page is current (`tests/test_reference_register_real.py`).
8. The dispatch hook still blocks a REQ brief without the line and allows the fixed sample (`tests/hooks/test_orchestrator_route_hooks.py`).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes (the new tests sit in the existing pytest run); (c) the checks are allow-lists: unknown kind, status, field shape or an unreadable file fails closed; the name ban keys on a hash of whole lower-cased words; (d) the register states a gate reads - no record, open, built, verified, deferred with issue, deferred without issue, decided, spec_change open - each tested for `--close-check`.
Threat model: in scope - a row closing with an open COPY gap, a difference kept without an ADR, a brief dropping an open record, the competitor's name entering public text through a record; out of scope - a record whose description of the reference behaviour is wrong (the study role and the verifier check content).
Findings checked: guard-as-forbidden-list, brief-rule-from-memory, dependent-tests-not-run-stale-later
Reviewer checklist: records validated by allow-lists; row/REQ cross-check against the real table; close-check
states all tested; label renamed everywhere with no rule loosened; page deterministic and checked in CI; the name never
written in any changed file; gate results quoted; no new duplicated literal; reuse the existing helper; ruff/mypy
baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
