# Verifier brief: the reference-product difference register and its gates (ADR-176), Tier A, round 2 (the last round)

Independent, adversarial verifier; you built none of it. READ-ONLY: never edit, create, commit or delete a tracked file
in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\0c676935-9a2f-45f8-b156-ae28fa0687d6\scratchpad\verify-register-r2`. Round 1 found two MAJOR holes (a COPY cleared as decided with no reason; the name
ban bypassed by escapes, splits, plurals, look-alike letters) - its scripts are in `...\scratchpad\verify-register\`
(attack.py, attack2.py): re-run them first, then attack the new code fresh. Also run the fixed tool with `--root
D:/Abhay/Ventures/OptionsForOptions2-builder-reqs --check` over the 120 loaded records (only the stale page may fail).

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-process`, branch `build/seq-process`, head e4f52ac2
(builder commits bca2fab0, 5ff66747, 472cc840; fix 1 e4f52ac2, brief process-reference-register-fix-1.md). Brief: `docs/process/builder-sequence-briefs/process-reference-register.md`
- run every item of its `Attack list:`. Spec: ADR-176 (every point), ADR-173 (2).
Reference: none - searched register, difference record (tooling); open records named: RD-001.

Attack first: (1) a row can close with an open COPY gap: find any record shape, status spelling, case, whitespace or
missing field that makes `--close-check` exit 0 while a COPY or spec_change record is open (it must fail closed);
(2) `check_brief.py`: a brief naming REQ-135 that drops RD-001 but still passes - multi-line Reference lines, the id in
another line, a lower-case id, RD-0010 vs RD-001, a REQ named only in a quote, a verifier brief; (3) `--check` passes a
DIFFERENT-BY-DECISION without a real ADR, a COPY whose row belongs to another REQ (use the real table, including a
"REQ-006 + REQ-007" cell), an over-long label, a duplicate id, a file name not equal to its id; (4) the name ban: the
reference product's name in any field, any case, inside punctuation or a URL, in a key, or split by a hyphen - which
pass? (the ban compares a sha256 of whole lower-cased words; say exactly what it misses); and confirm the name appears
in no file the builder committed (`git diff --name-only 83842bf3..472cc840` then scan); (5) the rendered page is
deterministic (render twice, compare) and `--check` fails when it is stale; (6) `tests/test_reference_register_real.py`
runs in the kit CI pytest run (it sits under `tests/`) and is not marked out; (7) delete each guard in scratch copies and
run `python scripts/orchestrator/mutation_gate.py` with your own mutants (results file in your scratch folder).
Run: `python -m pytest -q -p no:cacheprovider tests/orchestrator tests/hooks tests/test_reference_register_real.py`, the
guard tests and `-m repo_scan tests` once each (the builder did not re-run them after its last fix).
No database. BINDING: never stop a process by name. Kit guard: a shell command naming spec/, tools/, .claude, factory,
views or .github is blocked; use Read/Grep/Glob, or `--pathspec-from-file`.

Why Opus: Tier A - a gate every future row passes through; a hole lets a row close with a gap open or the competitor's
name reach the public repo.

Threat model: in scope - a row closing with an open COPY or spec_change record, a brief dropping an open record, a difference kept without an ADR, the competitor's name entering public text through a record; out of scope - whether a record's description of the reference behaviour is true.
Findings checked: guard-as-forbidden-list, brief-rule-from-memory, dependent-tests-not-run-stale-later

Return a JSON array, one object per point (1)-(5) of the register decision plus the brief line rule, with keys item,
result (pass / fail / partial), commands, observed (file:line), attack; then under 250 words: each
fail/partial with severity (CRITICAL / MAJOR / MINOR) and the smallest fix, and anything not checked.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
