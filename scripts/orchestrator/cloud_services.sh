#!/usr/bin/env bash
# cloud_services.sh: start the PostgreSQL 16 and Redis 7 that a claude.ai cloud container already has installed, and
# prepare the database the app suite needs (database ofo_test, the owner role, the ofo_app role with the ADR-048
# attributes, migrations to head). Idempotent. Does nothing outside a cloud session (CLAUDE_CODE_REMOTE != true), so
# it can never touch the owner's PC or the production database. Throwaway passwords, local to the container, the
# same values the CI workflow uses (.github/workflows/app-tests.yml).
#
#   bash scripts/orchestrator/cloud_services.sh [--reset]   # --reset drops and rebuilds ofo_test (a killed suite leaves rows
#                                                           behind that make the migration round-trip test refuse). Then:  python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py   (add -m "not full_chain" as CI does: the migration down-chain test is nightly-only)
#
# Exit 0 = ready (or not a cloud session), 1 = a step failed (the step is named on stderr).
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  echo "cloud_services: CLAUDE_CODE_REMOTE is not 'true'; not a cloud session, nothing started" >&2
  exit 0
fi

PGPASS=postgres_ci_dummy_pw
APPPASS=ofo_app_test_pw
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
step() { echo "cloud_services: $*" >&2; }
psql_su() { su postgres -c "psql -v ON_ERROR_STOP=1 -qtA $*"; }

step "start postgresql"
if ! pg_isready -q -h 127.0.0.1 -p 5432; then
  service postgresql start >/dev/null 2>&1 || { step "FAIL: 'service postgresql start' failed"; exit 1; }
  for _ in $(seq 1 30); do pg_isready -q -h 127.0.0.1 -p 5432 && break; sleep 1; done
  pg_isready -q -h 127.0.0.1 -p 5432 || { step "FAIL: postgresql not accepting connections on 127.0.0.1:5432"; exit 1; }
fi

step "owner password, database ofo_test, role ofo_app"
psql_su "-c \"ALTER USER postgres PASSWORD '${PGPASS}'\"" >/dev/null
if [ "${1:-}" = "--reset" ]; then
  step "reset: dropping ofo_test and every per-file copy of it"
  for db in $(psql_su "-c \"SELECT datname FROM pg_database WHERE datname LIKE 'ofo_test%'\""); do
    psql_su "-c 'DROP DATABASE IF EXISTS \"${db}\" WITH (FORCE)'" >/dev/null
  done
fi
if [ "$(psql_su "-c \"SELECT 1 FROM pg_database WHERE datname='ofo_test'\"")" != "1" ]; then
  psql_su "-c 'CREATE DATABASE ofo_test'" >/dev/null
fi
if [ "$(psql_su "-c \"SELECT 1 FROM pg_roles WHERE rolname='ofo_app'\"")" != "1" ]; then
  psql_su "-c \"CREATE ROLE ofo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 PASSWORD '${APPPASS}'\"" >/dev/null
fi
psql_su "-c 'REVOKE CONNECT ON DATABASE ofo_test FROM PUBLIC' -c 'GRANT CONNECT ON DATABASE ofo_test TO ofo_app'" >/dev/null

step "migrations to head (as the owner role)"
(cd "$ROOT" && ALEMBIC_DATABASE_URL="postgresql+asyncpg://postgres:${PGPASS}@127.0.0.1:5432/ofo_test" \
  python -m alembic -c backend/ofo_app/alembic.ini upgrade head >/tmp/cloud_services_alembic.log 2>&1) \
  || { step "FAIL: alembic upgrade head (see /tmp/cloud_services_alembic.log)"; exit 1; }

step "start redis"
if ! redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; then
  redis-server --daemonize yes --bind 127.0.0.1 >/dev/null 2>&1 || { step "FAIL: redis-server did not start"; exit 1; }
fi
step "ready: postgres 127.0.0.1:5432 (ofo_test, roles postgres and ofo_app), redis 127.0.0.1:6379"
