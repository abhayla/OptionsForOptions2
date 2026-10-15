# Builder brief: W-061 follow-ups - issues #138 (gaps 2-3) and #167 (review minors)

Core: the strategy store's database validator and the domain agree on every bound (a value the domain accepts is
stored; one it refuses is refused by both, with the domain's clean refusal first), only schema versions the domain
can load are storable, and the API's conflict and ownership answers are tested through the API.
Proof (step 1, red first against b38fbbf): (a) a strike of "1000000000000000000" (19 digits) or a contract_id >= 10^18
passes the domain today and is refused only by the database (23514 -> the save fails late through the error
boundary); a test asserts the DOMAIN refuses it with its fixed refusal; (b) a definition with schema_version 2 (column
also 2) is accepted by the database today and refused on load (`schema_version_unknown`); a raw INSERT as ofo_app with
version 2 must be refused; (c) two PUTs with the same `expected_revision` through the API -> the second answers 409;
(d) a PUT on another user's strategy -> the same answer GET gives for another user (not found), nothing stored.

Tier: A (a new migration changes a database guard). Model: sonnet/medium.
Budget: 40 min wall-clock, 60 tool calls. Commit after each item; at budget stop after a commit and report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~250 words.
Copy from: none.

## RCA and Class
- RCA: the W-061 round-3 positive validator and the domain value types were built from two lists of bounds; nothing
  forces them to agree (issue #167 items 1-2); the API-level conflict/ownership paths were tested only below the API.
- Class: every slot of the stored definition shape (both tables) and every API write path. Before: 2 bounds where the
  database is stricter than the domain, schema_version accepted beyond what loads; after: one source of bounds, an
  agreement test over every slot's extreme values (just inside / just outside each bound) for domain AND database.
- Detection: the agreement test (generated over the slot table), plus the two API tests.

## Spec basis
- REQ-038 AC-5: "live prices are never saved inside the strategy."
- ADR-069 decision: "short identifiers
  or numbers only - letters, digits, underscore, hyphen and dot, at most 64 characters"

## Do
1. **Bounds in one place:** the domain value types (strike, contract_id, quantity, risk-limit values) carry the same
   bounds as the database validator (read `backend/ofo_app/alembic/versions/0008_strategy_store.py` validator and
   `backend/ofo/strategy/` value types); the domain refuses first with its fixed refusal (never a late 23514).
2. **schema_version:** new migration `0010_strategy_schema_version` (down_revision `0009_minute_history`) re-creating the
   definition and change-item validators so schema_version must be one the domain knows (today 1); keep the md5 pins
   and the allowlist chain exactly as 0008 does (bump the pinned bodies); downgrade restores 0008's bodies; a
   real-DB downgrade-then-upgrade test.
3. **#167 item 4 wording:** validators marked IMMUTABLE that cast text to `date` become STABLE (or drop the marker);
   `render_change_items` enforces the same 1..100 item bounds as `stored_form.summary_text`.
4. **#138 gaps 2-3:** the two API tests above in `tests_app/test_strategy_store.py` (or the strategies API test file -
   grep first).
5. `docs/process/coverage-stages.yaml`: remove the `"#174"` row (closed with PR #182); regenerate with
   `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\coverage.py C:\Abhay\Ventures\OptionsForOptions2-w061f --write`.
6. The agreement test (step 1's detection): for each bounded slot, values at the bound and one past it, asserting the
   domain and the database give the same verdict.
Mutations (each must turn a test red): widen one domain bound so it differs from the database; let the DB accept
schema_version 2; drop the API 409 mapping; drop the user_ref filter on PUT.

## Rules (this PC's PostgreSQL also serves IPODhan production - probes < 30 s, targeted tests only)
- Grep tests/ and tests_app/ for every function, slot and code you change and run each file that names one.
  DB, from `C:\Abhay\Ventures\OptionsForOptions2`:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-w061f python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_store.py tests_app/test_strategy_closed_shape.py tests_app/test_strategy_shape_matrix.py tests_app/test_migration_sql_parses.py <new files>`;
  alembic via the same runner (`python -m alembic -c backend/ofo_app/alembic.ini upgrade head`; ofo_test is at 0009);
  leave the DB at your 0010 head. Domain: `python -m pytest -q -p no:cacheprovider tests/strategy` and
  `tests/errors` (one directory per call). CI mirror:
  `python C:\Abhay\Ventures\OptionsForOptions2\scripts\orchestrator\atool.py C:\Abhay\Ventures\OptionsForOptions2-w061f w061 --no-tests`.
- Kit guard: shell text must not name .claude, tools/, spec/requirements, .github or views. Do not edit kit files or
  `spec/`. Never write `evidence/`. Never mark anything verified. Push `fix/w061-followups`; no PR.
