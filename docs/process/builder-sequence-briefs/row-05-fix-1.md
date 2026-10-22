# Row 5 fix round 1: REQ-053 (W-133) - weekday-safe tests, parse off the event loop, AC-5 scan allow-list (Tier A)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files; fix
lint as you go, never as a last step).

Core: the staleness tests and the AC-5 scan give the same answer on every day of the week and miss no rule constant.
Proof: step 1 is a failing run of the three "tomorrow at 12:00" tests with the clock fixed to a Friday 14:00 IST
(verifier round 1 on ed1daf9c replayed: "Fri 14:00 -> tomorrow Sat unconfirmed = False").

Spec basis: REQ-053 AC-3: "Before a leg is added, the builder checks what Zerodha data allows and blocks legs that are
currently unavailable; the check repeats just before execution." REQ-053 AC-5: "Any Zerodha rule encoded in code
(market-order limits, SL-M limits on index options, freak-trade protection, OI and strike restrictions, basket
execution) cites a current Zerodha source and date; 'options are limit-only' is never hard-coded."
Copy from: none beyond the row brief's map rows.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Commit with
`git add <paths>` (never `-A`); do NOT push. Use the edit tools. Do NOT change any `verified` or `source` field in
`backend/ofo_app/order_limits_registry.py` except adding the two new entries below (the orchestrator updates sources
from a separate research run). DB tests: run them through the throwaway-database runner, which gives an empty
catalogue: `python D:/Abhay/scratch/ofo2-builder-sequence/fresh_launch.py D:/Abhay/Ventures/OptionsForOptions2-builder-reqs python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini <files>`
(about 5 minutes for four files; run it once at the end). Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row05-fix1`.

## Verifier round 1 findings to fix
1. AC-3: three DB tests build a date one calendar day after today and judge it at 12:00 (yesterday-unconfirmed,
   picker-not-loaded-today, pre-execution-registry-empty); on Fridays and Saturdays the judged day is a weekend day
   that maps back to Friday 08:00, so they fail. Use the next weekday after the load date; rename the "loaded today"
   docstrings and test names (`catalogue_picker.py:120,130`) to the session rule.
2. AC-3 minor: `parse_rows_naming_the_row` runs on the event loop (~0.29 s on a 115k-row list once an hour); run the
   parse in `asyncio.to_thread`; add a per-test timeout to the scheduler tests so a hang fails fast instead of at 60 s.
3. AC-5: the scan's name pattern has no LENGTH, so `ofo.execution.basket:MAX_TAG_LENGTH` (8) and
   `_LEGACY_TAG_MAX_LENGTH` (20) are missed; values it cannot read are skipped silently
   (`tests_app/test_zerodha_rules_cited.py:107-114`). Make the scope rule an allow-list: EVERY module-level UPPER_CASE
   constant with a numeric, string, tuple/frozenset-of-strings value in the scoped trees must be in `RULES` or in
   `NOT_A_ZERODHA_RULE` (with a reason); a value the scan cannot read fails closed. Add the two tag entries to `RULES`
   (source = the measured Kite InputException 2026-10-19 cited in basket.py, verified=False).

Attack list: (each names its test file)
1. The three tests with the clock fixed to every weekday 14:00 and to Saturday/Sunday 14:00 -> green each day
   (`tests_app/test_eligibility_from_zerodha.py`, `tests_app/test_catalogue_picker_api.py`).
2. A load whose parse takes 2 s (fake) -> the event loop serves a request meanwhile (`tests_app/test_catalogue_refresh.py`).
3. A planted `MAX_FOO_LENGTH = 9` in a scoped module, unlisted -> red; a planted constant whose value the scan cannot
   read -> red; the real tree -> green (`tests_app/test_zerodha_rules_cited.py`).
4. The two tag constants are found and listed (`tests_app/test_zerodha_rules_cited.py`).
5. No test in the row's files depends on today's weekday: run the row's test files with the clock frozen on a Friday
   and on a Saturday (same files).

Standing items: (a) the scheduler run keeps its timeout; the parse moves off the loop (test 2); (b) n/a: no CI step
changes; (c) the AC-5 scan is an allow-list over every UPPER constant in scope and fails closed; (d) the list answer
states stay tested.
Threat model: in scope - a CI run red only on some weekdays, a rule constant escaping the registry; out of scope - a constant built at runtime.
Findings checked: guard-as-forbidden-list, wall-clock-assertion-flakes-under-load

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the four DB files through the throwaway-database runner (once, at the end) and `python scripts/ruff_ratchet.py`.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
