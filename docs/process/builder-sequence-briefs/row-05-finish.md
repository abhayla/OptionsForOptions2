# Row 5 finish: REQ-053 eligibility read part (W-133), the first builder ran out of calls (Tier A, fix pair)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files).
Row brief: `docs/process/builder-sequence-briefs/row-05-REQ-053-eligibility.md` (read What to build and the Attack
list). This brief only finishes it.

Core: the catalogue the add-time check reads is the latest list Zerodha published for the current trading session.
Proof: step 1 is a failing test: a catalogue loaded Friday 2026-10-23 09:00 IST, checked on Saturday 10-24 11:00 IST,
answers `gate_contract_unconfirmed` at 03a9f377 (the "loaded today" rule); after the change it is current.

Spec basis: REQ-053 AC-3: "Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are
currently unavailable; the check repeats just before execution." (the before-execution repeat is order-path scope).
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`, head 03a9f377 (the first
builder's commit). Commit with `git add <paths>` (never `-A`); do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row05-finish`.

## What to do (orchestrator decisions, technical)
1. Staleness rule change: a catalogue is current when its latest successful load is at or after 08:00 IST of the
   most recent trading-session day (today when today is a weekday and the time is past 08:00; otherwise the previous
   weekday; no holiday calendar exists - say so in the code comment). On the database clock. Replace the "loaded
   today" check in all four reads (add-time check, picker offer, pre-execution registry and wherever else the first
   builder put it).
2. Hung download: the loader's fetch passes a socket timeout to the door (`kite_http.open_url`) so a hung download's
   thread ends; test that a fetch past the timeout ends with the timeout code and keeps the previous list.
3. Attack 4: an expired contract still present in the list (F-33: expired SENSEX rows in the 16:30 list) -> refused;
   one expiring today -> offered (`tests/execution/test_eligibility_from_zerodha_list.py`).
4. Attack 7: token 61746 reused after expiry -> the retired row never shadows the live one after a scheduled reload
   (`tests_app/test_contract_identity_lifecycle.py`; read the file first and extend its existing case).
5. Ruff: the ratchet is red on C416, E501, PLC0415, PLR2004, S608. Fix every rise in the files the row changed
   (`backend/ofo_app/catalogue_refresh.py`, `order_limits_registry.py`, `catalogue_load.py`, `catalogue_picker.py`,
   `eligibility_from_zerodha.py`, `main.py`, `tests/test_zerodha_rules_cited.py`, `tests_app/test_catalogue_refresh.py`,
   `tests_app/test_eligibility_from_zerodha.py`); a `# noqa: S608 constant table name` only where the project rule
   allows it.

Attack list: (each names its test file; run each before reporting)
1. Loaded Friday 09:00, checked Saturday 11:00 and Monday 07:30 -> current; checked Monday 09:00 with no Monday load
   -> unconfirmed (`tests_app/test_eligibility_from_zerodha.py`).
2. A load at 07:59 on a weekday checked at 09:00 the same day -> unconfirmed (before the publish time)
   (`tests_app/test_eligibility_from_zerodha.py`).
3. A hung fetch -> ends at the timeout, previous list kept, no thread left (`tests_app/test_catalogue_refresh.py`).
4. Expired contract still in the list refused; expiring today offered (`tests/execution/test_eligibility_from_zerodha_list.py`).
5. Token 61746 reuse after a scheduled reload (`tests_app/test_contract_identity_lifecycle.py`).

Standing items: (a) the scheduler run keeps its timeout and a test shows the request path is never blocked by a load;
(b) n/a: no CI step changes; (c) the AC-5 registry scan stays an allow-list and fails closed; (d) the list answer states
of the row brief stay tested.
Threat model: in scope - a leg saved against a list older than the current session's publish, a hung load that never
ends; out of scope - a forged list from a hijacked Kite host.
Findings checked: daily-load-misses-intraday-additions, guard-as-forbidden-list

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus every changed test file in full (DB files through `D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py
<worktree> ...`; tests that need an empty shared catalogue fail on #497 - report them by name, they run in CI) and
`python scripts/ruff_ratchet.py` (must be OK).
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
