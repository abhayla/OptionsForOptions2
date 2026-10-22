# Row 4 finish: REQ-117 capability flags (W-132), the previous builder stopped mid-change (Tier A, fix pair)

Common brief: docs/process/builder-brief.md (read its Budget hard-stop rule). The row brief is
`docs/process/builder-sequence-briefs/row-04-REQ-117-capability-flags.md`: read its What to build, Attack list and
Reviewer checklist; this brief only finishes it.

Core: a feature asks a named flag, and a missing, unknown or unloadable flag hides it with a plain reason.
Proof: the row brief's step-1 test (remove `basket_margin_quote` -> margin line hidden with the reason) passes on the
committed tree.

Spec basis: REQ-117 AC-4: "A flag that is missing, unknown or fails to load counts as off (fail closed); a test removes
one flag and shows the feature hidden, not shown." (all five ACs quoted in the row brief).
Copy from: none - as the row brief (no REQ-117 map row).

## State you start from
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1`. Committed: 22939820 (W-132:
margin line asks basket_margin_quote, broker-name scan, gates-never-read-flags tests). UNCOMMITTED, from the previous
builder, mid-change: renames `backend/ofo/broker/capabilities.py -> flags.py`, `kite_capabilities.py -> kite_flags.py`,
`tests/broker/test_capabilities.py -> test_broker_flags.py`; edits in `backend/ofo/execution/partial.py`,
`backend/ofo_app/kite_broker_reader.py`, `backend/ofo_app/routes/broker_capabilities.py`,
`tests/execution/test_flags_never_loosen_gates.py`, `tests/marketdata/test_provider_replaceable.py`,
`tests/test_history_not_shown.py`, `tests/test_one_broker_only.py`, `tests_app/test_broker_capabilities_route.py`,
`tests_app/test_flags_never_loosen_kill_switch.py` (its last note: "Rewrite the kill-switch test body cleanly"),
`tests_app/test_kite_broker_reader.py`; new `backend/ofo/broker/kite_flags.json`,
`frontend/tests/margin-line-flag-wire.test.js`, `tests/broker/test_held_triggers_unread.py`,
`tests/execution/test_gates_import_no_flags.py`. Read `git status` and `git diff` first.

## What to do
1. Finish the rename consistently (every import, no leftover `capabilities` module unless something still needs it -
   then say why) and the kill-switch test; make every file above consistent.
2. Check each row-brief item and Attack list item is covered by a committed test; list any that is not.
3. Run every changed test file in full (DB files through `D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py
   <worktree> ...`, 0 skipped), the Tests: line below, `python scripts/ruff_ratchet.py`, and the openapi drift test.
4. Commit with `git add <paths>` (never `-A`). Do not push.

Attack list: (the same as the row brief; confirm each has a test)
1. One flag removed from the Zerodha set -> margin line hidden with the reason (frontend test + flags test).
2. Unknown flag name -> off, no exception (tests/broker/test_broker_flags.py).
3. Flag data fails to load / malformed / a value missing source or date -> all off (tests/broker/test_broker_flags.py).
4. `broker == "zerodha"` and its variants planted in feature code -> the repo scan red; in a data-layer module -> green.
5. `broker_held_triggers` off and unread (tests/broker/test_held_triggers_unread.py).
6. All flags on vs all off -> margin, reconciliation block, market hours, kill switch, freeze limit identical
   (tests/execution/test_flags_never_loosen_gates.py, tests_app/test_flags_never_loosen_kill_switch.py).
7. Hidden reason names no broker; the capabilities route is GET-only and no input changes it
   (tests_app/test_broker_capabilities_route.py).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the broker-name scan names its scope by
path and fails closed on a file it cannot parse; (d) n/a: flags are declared data, no other system's answer is read.
Threat model: in scope - a feature shown when its flag is missing or unknown, a feature keyed on a broker name, a flag
that loosens a safety gate; out of scope - a forged flag object injected at runtime (ADR-098).
Findings checked: guard-as-forbidden-list, caller-supplied-verdict-trusted

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
