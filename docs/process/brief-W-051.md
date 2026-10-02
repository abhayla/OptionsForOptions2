# Builder brief: W-051 platform base and the trusted database clock

Core: the database, not the caller, stamps `recorded_at` on a ledger row and refuses an event dated outside
`recorded_at` +/- 60 seconds; the application role cannot update, delete or disable that guard.
Proof: as the NON-superuser application role on real PostgreSQL: (a) an insert passing `recorded_at` 2020-01-01 stores
the server `now()`; (b) an `event_at` 2 minutes off the stamp is refused and the transaction rolls back; (c) UPDATE and
DELETE are refused with permission denied; (d) `ALTER TABLE ... DISABLE TRIGGER` is refused. Step 1 of your work IS
this proof: write `tests_app/test_ledger_clock.py` and the migration first.

Why Opus: Tier A; the design of database privileges, ownership and a trigger that must be hard to bypass.
Budget: 60 min wall-clock, 120 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`, one row per claim, result line quoted).
Tier: A (a guard meant to be hard to bypass; a DB migration).

## Spec basis
- REQ-064 AC-2: "Audit and timeline records are append-only."
- ADR-023 (Q225 clarification): the recorded-at time "is stamped by the ledger from its own clock; a caller can never supply
  it. Every new event's own date (granted/effective) must lie within the clock-skew window of that stamp, both ways."
- ADR-023 Q256: "the clock-skew window is 60 seconds, both ways."
- ADR-046: app-tests.yml runs only when the API/web source trees, their tests, their dependency files or the workflow
  itself change; the kit's ci.yml is not edited.
- ADR-048: tests run as role `ofo_app` (LOGIN, NOSUPERUSER, NOCREATEDB, NOCREATEROLE, CONNECTION LIMIT 5,
  statement_timeout 30s); tests never fall back to SQLite; DB tests skip with a stated reason when TEST_DATABASE_URL is
  unset.
- ADR-047: copy first from algochanakya using the map in `spec/technical-design/legacy-reuse.md`.

## Copy from (legacy-reuse.md M1; source `D:\Abhay\Ventures\algochanakya` at commit bf9faf7)
Each copied file starts with a comment: `Copied/adapted from abhayla/algochanakya@bf9faf7:<path> (ADR-047)`.
- `backend/app/database.py` -> `backend/ofo_app/db.py` (ADAPT): keep `create_async_engine` (server_settings jit off),
  `async_sessionmaker(expire_on_commit=False)`, `Base(DeclarativeBase)`, `get_db`. DROP `convert_decimals_to_float`
  (lines 11-24, float money), `init_db`/`create_all`, the Redis code, and the host print.
- `backend/app/config.py` -> `backend/ofo_app/config.py` (ADAPT pattern): `pydantic_settings.BaseSettings` with
  `model_config = SettingsConfigDict(env_file='.env', extra='ignore')`; only `DATABASE_URL` (required) and `APP_ENV`.
- `backend/app/api/routes/health.py` -> `backend/ofo_app/routes/health.py` (database check only, no Redis).
- `server_default=func.now()` on `DateTime(timezone=True)` (`backend/app/models/users.py:20`).
- `backend/tests/conftest.py`: copy ONLY the `client` fixture pattern (`app.dependency_overrides[get_db]` +
  `httpx.AsyncClient(transport=ASGITransport(app=app))`); NOT its SQLite engine or `@compiles` shims.
- `backend/pytest.ini`: `asyncio_mode = auto`, `asyncio_default_fixture_loop_scope = session` into `pytest-app.ini`
  (testpaths = tests_app, pythonpath = backend). No allure/coverage addopts.
- `.github/workflows/backend-tests.yml` -> `.github/workflows/app-tests.yml` (ADAPT): `postgres:16` service with the
  `pg_isready` health check; Python 3.12; path filters per ADR-046 (`backend/ofo_app/**`, `tests_app/**`,
  `requirements-app.txt`, `pytest-app.ini`, `.github/workflows/app-tests.yml`, `frontend/**`); steps: install
  `requirements-app.txt`; as `postgres` create role `ofo_app` (ADR-048 attributes, password from a dummy CI value)
  and database objects via `alembic upgrade head` run as the owner role; then
  `python -m pytest -c pytest-app.ini -q` with `TEST_DATABASE_URL` for `ofo_app` and `TEST_ADMIN_DATABASE_URL` for the
  owner. No Redis service, no Codecov, no Allure.
- `backend/requirements.txt` pins -> `requirements-app.txt`: fastapi==0.123.5, starlette==0.50.0, SQLAlchemy==2.0.44,
  alembic==1.17.2, asyncpg==0.31.0, pydantic==2.12.5, pydantic-settings==2.12.0, httpx==0.28.1, uvicorn==0.38.0; add
  pinned pytest and pytest-asyncio versions that install on Python 3.12 and 3.13.
- `backend/scripts/generate_openapi.py` -> `scripts/generate_openapi.py` (point it at `ofo_app.main:create_app`).
- `.github/scripts/alembic-migration-guard.py` -> `scripts/alembic_migration_guard.py` (refuses an empty migration).
- `.pre-commit-config.yaml` (ADAPT): file hygiene, ruff, detect-secrets with a baseline, no-.env commit. Do not install
  hooks into the developer's git config.
- New (no legacy equivalent): `backend/ofo_app/main.py` with `create_app()` (no module-level app side effects, no
  `create_all`), a generic exception handler that returns the JSON body `{error: internal_error}` and logs the detail (never
  `str(exc)` to the client, unlike legacy `main.py:293-307`); async Alembic env (`alembic init -t async` shape) under
  `backend/ofo_app/alembic/` with explicit model imports; baseline migration.

## The clock design (required)
- Table `ledger_entries` (the generic base later ledgers use): `id BIGSERIAL PK`, `kind TEXT NOT NULL`,
  `event_at TIMESTAMPTZ NOT NULL`, `recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `payload JSONB NOT NULL`.
- BEFORE INSERT trigger function: `NEW.recorded_at := now();` then RAISE (SQLSTATE of your choice, documented) when
  `NEW.event_at` is outside `NEW.recorded_at - interval '60 seconds'` .. `+ interval '60 seconds'`. The 60 s lives in
  one place (a SQL constant in the migration, named after Q256).
- Ownership: the migration runs as an owner role (CI: `postgres`; later on the VPS: the admin), so `ofo_app` is NOT the
  table owner and therefore cannot ALTER/DISABLE TRIGGER or DROP. Grant `ofo_app` only `SELECT, INSERT` on the table
  and `USAGE` on its sequence. REVOKE everything from PUBLIC.
- A small repository in `backend/ofo_app/ledger.py`: `append(session, kind, event_at, payload) -> (id, recorded_at)`
  that never sends `recorded_at`.

## Tests (tests_app/test_ledger_clock.py; real PostgreSQL only)
- Connect as `ofo_app` with TEST_DATABASE_URL; skip the module with a reason when it is unset. Never SQLite.
- (a)-(d) from the Proof, each its own test; plus: an `event_at` 30 s off is accepted; the repository returns the
  DB-stamped `recorded_at`.
- Mutation tests (write them first, red): with an admin connection (TEST_ADMIN_DATABASE_URL), in a transaction that is
  rolled back, drop the trigger and show test (a) would fail; grant UPDATE to `ofo_app` and show (c) would fail.
- `tests_app/test_health.py`: `GET /health` returns 200 with the database reachable (client fixture pattern).
- Expected values come from the spec text above, never from running the code under test.

## Standing items (run-discipline B4)
- Fail closed: any path the trigger cannot decide (NULL `event_at`) is refused, and a test proves it.
- Name the guard by what it is (the trigger and the grants), not by an identifier string search.
- A CI step that imports non-builtin packages runs after the dependency install step.
- The kit CI must stay green: `backend/ofo/` stays standard-library and never imports `ofo_app`; nothing under `tests/`
  imports fastapi, sqlalchemy or asyncpg (the kit CI installs only pyyaml, jsonschema, pytest).

## Rules
- Work only in your worktree. Do not edit kit files (`tools/`, `.claude/rules/kit/`, `.claude/hooks/`,
  `.claude/agents/`, `.claude/skills/deliver|intake`, `factory/schemas/`, `.github/workflows/ci.yml`, `KIT_VERSION`).
- Never write `evidence/` files or mark anything verified.
- Money is never float. No secrets in any file: CI passwords are dummy values in the workflow; real ones come from env.
- Run targeted tests only; log long output to a file and show the tail. Before you finish run
  `python -m pytest -q -p no:cacheprovider` (domain suite must still pass: 1,413+ tests) and
  `python -m pytest -c pytest-app.ini -q` (DB tests will SKIP locally: no TEST_DATABASE_URL yet; say so).
- Commit on your branch with a clear message; do not push or open a PR.
