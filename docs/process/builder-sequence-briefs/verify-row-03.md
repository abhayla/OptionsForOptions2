# Verifier brief: builder sequence row 3 (REQ-054 broker adapter, read part / W-131), Tier A

Independent, adversarial verifier; you did not build this. READ-ONLY: never edit, create, commit or delete a file in
any checkout (no in-place mutation); scratch and mutation copies only in
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\verify-03`.

Code under test: worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`; the row-3
build is every commit from 6d5d472a to the head named in your prompt (W-131 commits plus the orchestrator's real
fixture `tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json`). Other agents may commit unrelated files
(process tooling under scripts/hooks, scripts/orchestrator/check_brief.py) while you work: judge only the W-131 diff.
Spec: `spec/requirements/REQ-054.md` and its ADRs (ADR-054, ADR-057, ADR-058, ADR-059, ADR-081). Builder brief:
`docs/process/builder-sequence-briefs/row-03-REQ-054-broker-reader.md` - run every item of its `Attack list:` again.

Scope: AC-1 READ parts (authenticate, fetch account, fetch margin, fetch positions, fetch orders, fetch order status);
the basket and reconcile parts are deferred (order path, ADR-165): report them `deferred`. AC-2 (only Zerodha). AC-3
and AC-4 were measured built on main (per-broker table, identity lifecycle; lot/tick/freeze with dates): re-check them
against the diff and their tests, they must not regress.

Real data: the profile fixture is a real 2026-10-22 reply (redacted). Check the tests use it. Do NOT call Kite
yourself; the live API on :8765 is not needed for this row.

Tests: domain `python -m pytest -q -p no:cacheprovider tests/<file>.py`; app (targeted files only; the shared DB also
serves another product's production) `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/<file>.py`
(a skipped DB test counts as NOT run: report it). Known environment issue: tests asserting an empty shared catalogue
fail (#497).

Why Opus: Tier A (broker adapter, auth/tokens path, PII from the profile reply); adversarial checks across the door, the
allow-list and the reader.

Return a JSON array, one object per AC (and per AC-1 sub-part): `{"row": 3, "req": "REQ-054", "ac": "AC-n", "result":
"pass" | "fail" | "partial" | "deferred", "commands": "...", "observed": "... file:line", "attack": "..."}`, then
under 250 words: each fail/partial with the smallest fix, and anything not checked and why.
Budget: 40 min wall-clock, 70 tool calls
Report: evidence-table
