# Process item fix 1 (the last round): the reference register - decided needs a reason, the name ban reads decoded text

Common brief: docs/process/builder-brief.md (Budget hard stop: at 32 calls start nothing new, commit, report). Run
`python scripts/orchestrator/mutation_gate.py` on the verifier's mutants (V19 included) plus your own before reporting;
write the results to a file in your scratch folder and quote it (R18).
Size: S, 4 files, 4 items
CI: kit tests job (`tests/orchestrator/test_reference_register.py`, `tests/orchestrator/test_check_brief.py`; vars: none). No database.
Expected (orchestrator, before dispatch, clock 13:4x read at writing): 30 min / ~140k. A failed check after this round PARKS the register (the gates stay prose).

Core: a COPY record cannot clear the close gate as `decided` without a recorded reason, and the reference product's name
cannot pass `--check` in any encoding the verifier used.
Proof: step 1 - the verifier's two MAJOR cases fail first on the real tool at 472cc840: a COPY record `status: decided`
with no `adr` and `bug: false` -> `--close-check` exits 0 (red); a record holding the name as JSON \u escapes -> `--check`
exits 0 and the page holds the name (red). Both flip after the fix. The verifier's scripts:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\verify-register\attack.py`, `attack2.py`.

Spec basis: ADR-176 (2) a row does not close while a COPY record is open "unless it is deferred with an issue"; (5) a
measured bug is never copied; an approved extra goes on one batched SPEC CHANGE list; (4) new text never names the
reference product.
Copy from: none.
Reference: none - searched register, name ban (tooling); open records named: RD-001.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`. Commit with `git commit -F <msg>
-- <your paths>` (or `--pathspec-from-file`); do NOT push. NEVER stop a process by name. NAME RULE: never write the
reference product's name in any file, test or commit; build it from bytes at run time in tests. Scratch:
`...\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\proc-register-fix1`.

## What to do
1. MAJOR gate: `decided` clears a record only when it carries its reason - a DIFFERENT-BY-DECISION with a real `adr`;
   a COPY with `bug: true`; a COPY with `spec_change: true` AND a real `adr` (the owner's answer). Any other `decided`
   is a `--check` error and blocks `--close-check`.
2. MAJOR name ban: run the ban over every DECODED key and value (after json.loads), not the raw text; reduce each string
   to lower-case ASCII letters only and compare the sha256 of every window of the name's length; reject any non-ASCII
   letter in a record (look-alike letters). Cases from the verifier, each a test: split by hyphen, space or dots, plural,
   digit suffix, camelCase, zero-width space, \u escapes, a Cyrillic look-alike.
3. MINOR: refuse a record with a duplicate key on load (`object_pairs_hook`).
4. MINOR: `check_brief.py` ignores a `Reference:` line inside a code fence; a brief naming the requirement only as
   lower-case `req-135` is treated as naming REQ-135; a test that RD-0010 does not satisfy RD-001 (kills V19).

Attack list: (each names its test file)
1. COPY decided with no reason -> `--check` 1 and `--close-check` 1; each of the three valid decided shapes -> 0 (`tests/orchestrator/test_reference_register.py`).
2. The nine name-ban cases each fail `--check`; ordinary words containing no window of the name pass (same file).
3. A duplicate-key record fails on load (same file).
4. A fenced Reference line does not satisfy the brief rule; lower-case req-135 needs RD-001 (`tests/orchestrator/test_check_brief.py`).
5. RD-0010 never satisfies RD-001 (same file); every earlier test still passes; the verifier's mutants all killed.

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) both checks are allow-lists that fail closed: an unknown decided shape blocks, a non-ASCII letter is refused, the ban compares hashes of decoded letter windows; (d) the record states the close gate reads - open, built, verified, deferred with or without issue, decided with each reason and with none - each tested.
Threat model: in scope - a gap closing with no reason, the name reaching the public page through any encoding the verifier tried; out of scope - a deliberate misspelling that no longer reads as the name.
Findings checked: guard-as-forbidden-list, brief-rule-from-memory
Reviewer checklist: decided needs its reason; ban on decoded letter windows; non-ASCII letters refused; duplicate keys
refused; fenced lines skipped; V19 killed; gate results quoted; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
