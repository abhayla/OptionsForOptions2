# Builder brief: W-096 round 3 - on the final base: the core 500, two repo scans (Tier A: order state)

Core: `tests_app/test_execution_return.py::test_core_real_order_return_entry_then_exit` GREEN on the real replies
(plan 1 closed filled 65, 0 mismatches; plan 2 closed exited, strategy exited, P&L -130.00; replay changes nothing).
Proof: the DB test file, run once through the main checkout's `db_run.py` with your worktree as cwd (the shared test DB
is at main's head 0016 - no upgrade or downgrade needed unless your branch adds a migration; it must not).

State: PR #358 (draft) CI on c86cada: 9 failed in tests_app, 2 in the domain suite. Most come from the OLD base the
branch carries (W-094 before its fixes, W-095 round 3): they go away when you merge main (W-094 merged as #357,
W-095 as #359 by the time you start - check `git log origin/main --oneline -5`; if #359 is not on main yet, merge
`origin/build/W-095-execute-route` instead). Three failures are this item's own:
1. `test_core_real_order_return_entry_then_exit` and the two new route tests: 500, `KeyError: 'plans'` (the route).
2. `tests/marketdata/test_provider_replaceable.py::test_nothing_outside_the_kite_adapter_imports_the_kite_modules`:
   `backend/ofo_app/execution_return.py` / `routes/execution_return.py` import the Kite adapters (`kite_reads`,
   `kite_replies`). Pattern used by W-095 (#359): a module that wires Kite clients is a composition root and is
   listed in `BROKER_ADAPTER_PATHS` WITH a reason; pure logic must not import them (keep the matching/classifying
   module free of Kite imports if you can - take parsed domain values from the route).
3. `tests/strategy/test_templates.py::test_no_template_id_or_name_in_backend_code` - re-run after the merge; if it
   still names a line of yours, a `.name ==`/`.id ==` comparison to a string literal is the trigger.

RCA: the branch was built and checked on a base that changed under it (three parallel items), and two repo-wide
scans live outside the files a builder runs (finding repo-wide-scan-outside-targeted-tests, 7 occurrences).
Class: every failure on #358 - before 11; after 0 on the merged base.
Proof: the full domain suite once (`python -m pytest -q -p no:cacheprovider`, no DB, ~3.5 min) + the DB test file +
`tests_app/` non-DB files you touch.

Tier: A. Model: opus.
Why Opus: Tier A order-state route; a 500 in the core path whose cause is not yet known.
Budget: 40 min wall-clock, 44 tool calls. HARD limit: at call 41 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, `git status --short` empty.
Copy from: none - fixes in this item.
Findings checked: repo-wide-scan-outside-targeted-tests, builder-report-describes-uncommitted-work,
branch-migration-tests-move-shared-db
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
    reconciles them (REQ-057, REQ-060); a basket the user closed or only partly placed is handled as a partial
    execution (REQ-058), never retried automatically."

## Rules
- `git fetch origin && git checkout -B w096-r3 origin/build/W-096-return-route && git merge origin/main`; push with
  `git push origin HEAD:build/W-096-return-route` (PR #358 picks it up).
- Regenerate `docs/api/openapi.json` (`python scripts/generate_openapi.py`) if `tests_app/test_openapi_drift.py` fails.
- One DB run, last: `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py <your worktree> python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_execution_return.py`;
  then `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run.py D:/Abhay/Ventures/OptionsForOptions2 python -m alembic -c backend/ofo_app/alembic.ini current`
  (must print main's head). Never copy .env; never atool.py; no PR action.
- Before push, each as its own command: the full domain suite, `python scripts/ruff_ratchet.py`.
- No change to `execute_plan.py` / `routes/execute.py` behaviour. No kit or `spec/` edit, no `views/`, no `evidence/`.
