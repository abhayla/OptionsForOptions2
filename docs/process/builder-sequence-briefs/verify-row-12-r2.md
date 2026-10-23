# Verifier brief: builder sequence row 12 (REQ-072 AC-2 / W-140), Tier A, ROUND 2 - FINDINGS ONLY (ADR-178 (1))

Independent, adversarial verifier; you did not build this and you did not run round 1. READ-ONLY: never edit, create,
commit or delete a tracked file in any checkout; scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\verify-12r2`.

Scope (ADR-178 (1)): re-check ONLY round 1's finding and the two files the fix changed.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-next-12`, branch `build/seq-row-12`, commit
d76cd0e0 (parent fb9a3702). Files: `backend/ofo/outcome/service.py`, `tests/outcome/test_spot_gate_reason.py`. Fix
brief with the finding and attack list: `docs/process/builder-sequence-briefs/row-12-fix-1.md` (in the
`-builder-reqs` checkout). Spec: `spec/requirements/REQ-072.md` AC-2 and AC-3, ADR-015.

Round 1 finding (rows 12-14 verifier): with the index quote missing and the chain present, the reason read "the forward
price could not be derived from the option chain" because forward errors were collected before the spot gate.

Orchestrator ruling before you start: the fix brief's item 2 ("index stale -> refused as unusable") was WRONG. REQ-072
AC-3 keeps a stale index COMPUTED with a stale label; the builder kept it computed. Judge the stale case against AC-3,
not against the brief.

Check, each with pass/fail and file:line:
1. Index missing + chain present (the real recorded frames `tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz`
   with the NIFTY index quote removed) -> `outcome_spot_missing`, nothing computed (no P&L, no IV).
2. Index unavailable / last price 0 -> the spot reason, nothing computed.
3. Index stale -> computed with the stale label per AC-3 (not refused).
4. Index good + chain missing -> the forward reason, unchanged.
5. Both missing -> the index reason.
6. Only the gate order changed: no change to what is computed in the success path (read the diff of service.py).
7. Two mutants via `python scripts/orchestrator/mutation_gate.py`: move the spot gate back after the forward errors;
   drop the missing-spot branch. A test must fail on each. Results to your scratch folder.

No database. Why Opus: Tier A - `backend/ofo/outcome/service.py` is an outcome file in the safety set (it decides
whether P&L numbers are shown or refused).
BINDING: never stop a process by name; stop only PIDs you started. Kit guard: a shell command naming spec/, tools/,
.claude, factory, views or .github is blocked; use Read/Grep/Glob.

Return a JSON array, one object per check: `{"row": 12, "req": "REQ-072", "ac": "AC-2", "result": "pass" | "fail" |
"partial", "commands": "...", "observed": "... file:line", "attack": "..."}`, then under 150 words: each fail/partial
with severity and the smallest fix, and anything not checked.
Reference: none - searched index missing, spot unavailable, forward price (no open difference records for REQ-072).
Tests: python -m pytest -q -p no:cacheprovider tests/outcome; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 15 min wall-clock, 20 tool calls
Report: evidence-table
