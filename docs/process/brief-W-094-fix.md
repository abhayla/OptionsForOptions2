# Fix brief: W-094 round 2 - migration 0016 joins the app-role allow-list check, and the review MINORs (Tier A: migration)

Core: migration 0016 extends the ADR-048 app-role allow-list exactly like 0013 does (`extended_allowlist_sql`, the
post-phase check of exact grants, guard trigger on, pinned guard body), so a later wider grant or a dropped trigger on
`execution_plans` / `execution_plan_orders` fails the migration chain.
Proof: CI (its own PostgreSQL) runs the migration replay and allow-list tests; locally only the non-DB checks below.
The shared test DB is in use by another builder: do NOT run alembic or any DB test locally this round.

RCA: 0016 was written from the store's needs, not from the migration chain's contract that every table migration
extends the previous migration's allow-list (0007:253, 0008:629, 0013:92-124/128/157/177).
Class: every table created by a migration after 0006 must appear in the allow-list post-phase; before: 0016's two
tables missing, after: 0; a 0017 calling `_PREVIOUS.extended_allowlist_sql()` keeps working.
Proof: CI run of `tests_app/` migration/allow-list files green on the PR.

Tier: A (migration, order-safety tables). Model: sonnet.
Budget: 35 min wall-clock, 40 tool calls. HARD limit: at call 37 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words.
Copy from: migration `0013_exchange_freeze_limits.py` (this repo) - its allow-list extension and its column-limited
INSERT grant are the pattern; not legacy code.
Findings checked: store-rule-enforced-per-call-site, privilege-guard-as-denylist, branch-migration-tests-move-shared-db,
state-read-after-await, guard-without-killing-test
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- ADR-048 (database tests run as the limited `ofo_app` role; its grants are an exact allow-list checked by the chain).
- ADR-050 item 4: "(b) persist the order intent before sending"

## Fix (review findings, all in this round)
1. MAJOR: add `extended_allowlist_sql()` to 0016 and the post-phase check, copying 0013's shape exactly (0013:92-128,
   157, 177): the two new tables' exact grants, the guard triggers present, the pinned guard bodies.
2. MINOR: `ofo_app` INSERT on `execution_plans` limited to `(strategy_id, plan_number, action)` (status defaults to
   `open`, timestamps from the database clock), like 0013:156; the docstring's "closed_at is set from the database
   clock" then holds for INSERT too. Add a CHECK or trigger so a row cannot be INSERTed `closed`.
3. MINOR: the order guard's open-plan EXISTS (0016:111-112) takes `FOR SHARE` on the plan row, so a raw order/fill
   insert cannot slip in beside a concurrent close.
4. MINOR: a clash on `execution_plans_pkey` maps to `plan_open`-style `bad_plan` with its own message, not
   `tag_taken`; only the tag unique constraint maps to `tag_taken`.
5. MINOR: `close_plan(reason in ("filled","exited","partial"), filled=None)` is refused (`bad_plan`): a close that
   changes position must carry the quantities (restart rebuilds positions from them). `nothing_placed` with
   `filled=None` stores 0 for every order.
6. MINOR: the two-connection test's cleanup must not need superuser (`session_replication_role` requires it): delete
   its own rows in an order the guards allow, as the owner role through the existing test fixture, or use the test's
   own transaction; if a row cannot be removed, the test fails loudly (never leaves rows that make a later replay
   downgrade refuse).
7. Guard without a killing test: the identity-column checks in the plan guard (0016:77-78) - add a test as the OWNER
   role (the fixture that runs migrations) that hits the guard's own error code, or remove the check if the column
   grants already make it unreachable for every role but the owner (say which).

## Rules
- Branch: `git fetch origin && git checkout -B land/W-094 origin/land/W-094`; push to `land/W-094`.
- Non-DB checks before push, each as its own command: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_*.py`,
  `python scripts/ruff_ratchet.py`, `python scripts/alembic_migration_guard.py`,
  `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_migration_sql_parses.py` (parses only).
- No alembic command and no DB test locally this round (another builder holds the shared DB). No `atool.py`.
- No kit or `spec/` edit, no `views/`, no regenerated files, no `evidence/`. No PR (the orchestrator opens it).
