# Builder brief: #285 - renumber gate_price_outside_circuit off MARKET_DATA_120 (Tier B)

Core: after the change every (ErrorClass, number) code in the catalogue is unique with an EMPTY known-duplicates
allow-list, and `marketdata_disconnected` keeps MARKET_DATA_120.
Proof: `tests/errors/test_template_codes_unique.py` passes with `KNOWN_DUPLICATES` emptied (it fails on origin/main if
you empty the list before renumbering - show that red first).

Model: sonnet.
Budget: 15 min wall-clock, 30 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 200 words.
Copy from: none - a one-number change in this repo's error catalogue.

## Class (defect-fix contract)
- RCA: codes were chosen by hand per branch; W-078 (#267) took MARKET_DATA_120, already used by
  `marketdata_disconnected`.
- Class: every pair of templates sharing a code; on origin/main after PR #286 the guard allow-lists exactly one pair.
  Before: 1 pair; after: 0.
- Proof: the guard red with the empty allow-list before the renumber, green after.
- Detection: the guard (added in #286) is the detection; after this change it has no exceptions.

## Where
- Your own worktree, new branch `fix/285-md-120` from `origin/main` (must contain PR #286; check
  `tests/errors/test_template_codes_unique.py` exists, else stop and report).
- `backend/ofo/errors/templates.py`: `_gate("gate_price_outside_circuit", _MD, 120, ...` -> `123` (121 and 122 are
  taken by `gate_price_band_unknown` / `gate_price_not_known`; confirm 123 is free with a grep for `_MD, 123`).
- Keep `marketdata_disconnected` at 120: `tests/errors/test_messages.py:706` and the owner-facing table
  `docs/process/w024-templates-for-owner.md:80` name it.
- Empty the `KNOWN_DUPLICATES` allow-list (remove the variable or make it empty, keeping the test's structure clear).
- Grep the whole repo (backend, frontend, tests, tests_app, docs) for any other place that names the circuit template's
  code and update it. `tests/errors/template_pins.json`: the code is not part of the pin hash; run the pin test to
  confirm.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/errors tests/execution`.
- Commit and push `fix/285-md-120`; do not open the PR; never write `evidence/`, `work/` or the spec.
