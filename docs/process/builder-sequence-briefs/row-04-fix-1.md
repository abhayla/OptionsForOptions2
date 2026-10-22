# Row 4 fix round 1: REQ-117 AC-3 broker-name scan as an allow-list (W-132, Tier A, fix pair)

Common brief: docs/process/builder-brief.md (Budget hard stop; scratch-copy mutations; full changed test files).
Row brief: `docs/process/builder-sequence-briefs/row-04-REQ-117-capability-flags.md`.

Core: any broker word in feature code is a finding unless its file and line are on a short, reasoned allow-list.
Proof: step 1 is a failing test with the verifier's bypass `b.startswith('zerodha')` planted in a scratch feature
module, which the current scan passes (verifier round 1 on 2e0cea66); after the change it is red.

Spec basis: REQ-117 AC-3: "A repo test fails if feature code compares a broker name or id (for example "zerodha")
instead of a flag." Finding guard-as-forbidden-list: a guard states what IS allowed and refuses everything else.
Copy from: none - project test, no legacy row.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (head f18611aa; code as
2e0cea66). Commit with `git add <paths>` (never `-A`); do NOT push. Scratch:
`C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row04-fix1`.

## Verifier round 1 findings to fix
1. AC-3 PARTIAL: `tests/test_no_broker_name_in_feature_code.py` refuses only listed shapes (`==`, `!=`, `in`, the
   `ZERODHA` constant, `'kite'`, JS `===`, `includes`); 19 unlisted shapes pass. Python: `b.startswith('zerodha')`,
   `'zerodha'.__eq__(b)`, `'ZerodhaKite'`, `type(r).__name__=='KiteBrokerReader'`, `isinstance(r, KiteBrokerReader)`,
   `from ofo.instruments.models import ZERODHA as Z; b==Z`, a local alias, `T.get('kite')`, a module-level set,
   `S.__contains__`, SQL text `broker = 'zerodha'`. JS: `const Z='zerodha'; b===Z`, `BROKER`, `.some`, a multi-line
   `includes`, a camel-case literal, `MAP['zerodha']`, a regex test, `Object.is`. Real case: `routes/broker_status.py:49`
   (`_ACTIVE` SQL with `broker = 'zerodha'`).
2. MINOR AC-2: `funds_read` cites `backend/ofo_app/kite_reads.py` for `GET /user/margins`; the call is in
   `backend/ofo_app/kite_margin.py:36`.
3. MINOR AC-4: a duplicate JSON key in `kite_flags.json` wins silently (a second `broker_held_triggers` with `on: true`
   -> all on). Refuse duplicate keys at load (all flags off).

## What to build (orchestrator decisions, technical)
- The scan becomes an allow-list: in feature code (same path scope as today: `backend/ofo_app/routes/`,
  `backend/ofo/strategy/`, `backend/ofo/outcome/`, `frontend/src/`), ANY occurrence of a broker word (case-insensitive
  `zerodha`, `kite`, and the names `KiteBrokerReader` / any `Kite*` class, the `ZERODHA` / `BROKER_ZERODHA` constants and
  any import alias of them, resolved by AST for Python and by token scan for JS/Vue) is a finding unless its
  `path:line-text` is in an allow-list module next to the test, each entry with a one-line reason (e.g. the
  "Margin (Zerodha)" label in `MarginLine.vue`, the Settings page's broker name, fix codes like `connect_zerodha`).
  Comments and docstrings are ignored by AST for Python; for JS/Vue, comments are stripped before the scan. Fail closed
  on a file it cannot parse. An allow-list entry whose line no longer exists is itself a failure (stale entry).
- `routes/broker_status.py:49`: move the broker-session query into the session store module
  (`backend/ofo_app/broker_token_store.py` or its neighbour) - data layer, outside the feature scope - and import it.
- Fix the `funds_read` source; refuse duplicate keys in the flag file (`object_pairs_hook`), test it.

Attack list: (the final verifier runs each; run each yourself first; each names its test file)
1. All 19 verifier shapes above planted in scratch feature modules -> red each (`tests/test_no_broker_name_in_feature_code.py`).
2. The same text in a data-layer module (catalogue store, broker adapter, session store) -> green (same file).
3. An allow-list entry for a line that no longer exists -> red (same file).
4. A broker word only in a comment or docstring -> green; a `.vue` file with two `<script>` blocks -> both scanned.
5. Duplicate key in `kite_flags.json` -> all flags off (`tests/broker/test_broker_flags.py`).
6. `funds_read` source path exists and names the margins call (`tests/broker/test_broker_flags.py`).
7. The real tree -> green, and the allow-list has a reason on every entry (same scan test).

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the scan is an allow-list, resolves
aliases by import source, and fails closed on a file it cannot parse; (d) n/a: no other system's answer.
Threat model: in scope - feature code keyed on a broker name in any shape the language allows; out of scope - code
built from strings at runtime (`getattr(m, 'Ki' + 'te')`), recorded as a known limit.
Findings checked: guard-as-forbidden-list
Reviewer checklist: every one of the 19 shapes red; stale allow-list entries red; data layer green; the moved query
keeps the status route's behaviour (its tests pass); every changed test file in full, DB files through the main
checkout's db_run.py with 0 skipped; scratch-copy mutation list; no new duplicated literal; reuse the existing helper;
ruff/mypy baselines must not rise; targeted tests only; no regenerated files.

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
