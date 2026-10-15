---
work_item: W-076
ac: AC-4
requirement: REQ-054
ac_fp: "739ca370dc58"
result: pass
verified_by: "verifier (opus, fresh context)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "pytest tests/instruments tests/execution tests/errors tests/test_fixture_symbols.py tests/test_door_names_private.py; db_run.py pytest -c pytest-app.ini tests_app/test_freeze_store.py tests_app/test_freeze_allowlist_chain.py tests_app/test_migration_sql_parses.py; db_run.py alembic current; own probe of parser + execution_review on the real fixture row; 0013 import check; template pin diff; tools/ac_fp.py REQ-054 AC-4 --yaml"
---

AC: AC-4
result: pass
commands: as in the frontmatter (verified at 5e82f92)
observed: 1460 passed; 464 passed, 0 skipped (DB at 0013 head); real row 47185 MaxTradQty 3.511000E+03 MinLot 65 -> freeze_limit 3511, file_date 2026-10-15; 3510 units executable, 3575 blocked with the reason and limit 3511 / max 3510 (54 lots); stored (NSE_FO,47185) -> (3511, 2026-10-15)
attack: units==limit blocked; omitted arg TypeError; None/unknown/ambiguous symbol -> warning; older file never replaces newer; same-date different limit refused; future date refused (loader + DB guard); app role cannot UPDATE/DELETE; 0013 chains on 0012_charge_rates keeping block 13 and adding 14; per-exchange storage settled by ADR-081's consequence. Defects (minor, none blocking): REQ-054 body said the load day from the DB clock while ADR-081 stores the file's date (REQ-054 text reworded in this PR); a concurrent same-date load race (#263); the block is not yet acted on by a send path (W-080 calls it); a non-lot-multiple quantity errors the review (fails safe).

Recorded by the orchestrator from the verifier's returned block.
