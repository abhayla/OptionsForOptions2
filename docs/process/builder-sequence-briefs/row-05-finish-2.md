# Row 5 finish 2: REQ-053 (W-133) - attacks 4 and 7, ruff ratchet green, full runs (Tier A, size M)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files).
Row brief: `docs/process/builder-sequence-briefs/row-05-REQ-053-eligibility.md`; previous finish brief
`row-05-finish.md` (its items 1-2 are done at 93c6097f).

Core: the catalogue the add-time check reads is the latest list Zerodha published for the current trading session.
Proof: `tests_app/test_eligibility_from_zerodha.py -k "friday or publish"` passes at 93c6097f (2 passed); this round
keeps it green and adds the two missing attacks.

Spec basis: REQ-053 AC-3: "Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are
currently unavailable; the check repeats just before execution." REQ-053 AC-2: "The contract catalogue (what exists)
is stored separately from current eligibility (what Zerodha permits); contracts are never permanently deleted because
they are unavailable today."
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 93c6097f. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools (heredocs and multi-command shell lines are refused).
Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row05-finish2`.

## What to do
1. Attack 4: an expired contract still present in the list (F-33: expired SENSEX rows in a 16:30 list) -> refused;
   one expiring today -> offered (`tests/execution/test_eligibility_from_zerodha_list.py`, using the real slice
   fixtures under `tests/fixtures/eligibility/` or `tests/fixtures/instruments/`).
2. Attack 7: token 61746 reused after expiry -> the retired row never shadows the live one after a scheduled reload
   (`tests_app/test_contract_identity_lifecycle.py`; read it first and extend its existing case).
3. `python scripts/ruff_ratchet.py` must print OK. It is red on C416, E501, PLC0415, PLR2004, S608 (50 findings in
   the row's changed files, mostly `tests_app/test_catalogue_refresh.py` and `tests_app/test_eligibility_from_zerodha.py`):
   long lines, named constants for magic numbers (HTTP codes from the test module's existing constants if any), the
   local imports in the new hung-fetch test moved to the top, `list()` for C416, and S608 only with the project's
   `# noqa: S608 constant table name` where the f-string interpolates a module constant table name.
4. Run the DB-backed files in full through the main checkout's db_run.py (0 skipped):
   `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_eligibility_from_zerodha.py tests_app/test_catalogue_refresh.py tests_app/test_catalogue_picker_api.py tests_app/test_contract_identity_lifecycle.py`
   Tests that need an empty shared catalogue fail on #497: list each by name; do not "fix" them by deleting rows.

Attack list: (each names its test file)
1. Friday 09:00 load current on Saturday 11:00 and Monday 07:30, stale Monday 09:00 (`tests_app/test_eligibility_from_zerodha.py`).
2. Expired contract still in the list refused, expiring today offered (`tests/execution/test_eligibility_from_zerodha_list.py`).
3. Token 61746 reuse after a scheduled reload (`tests_app/test_contract_identity_lifecycle.py`).
4. The test-only "judged at 12:00 IST of a pinned date" seam cannot apply outside APP_ENV=test (`tests_app/test_eligibility_from_zerodha.py`).
5. The ratchet prints OK and the guard + repo_scan sets pass (commands below).

Standing items: (a) the scheduler keeps its timeout and the request path is never blocked (existing test stays
green); (b) n/a: no CI step changes; (c) the AC-5 registry scan stays an allow-list and fails closed; (d) the list
answer states stay tested.
Threat model: in scope - a leg saved against a stale list, the test date seam reachable in production; out of scope - a
forged list from a hijacked Kite host.
Findings checked: daily-load-misses-intraday-additions, guard-as-forbidden-list

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table
