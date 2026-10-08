"""db_run.py <cwd | agent:<id>> <command...>: run a command with the ADR-048 test-database variables set; prints no secret.

TEST_DATABASE_URL (the limited ofo_app role) comes from the project .env. The owner URL (ALEMBIC_DATABASE_URL,
TEST_ADMIN_DATABASE_URL) is built in memory from GLOBAL.env's WINDOWS_VPS_PG_ADMIN_USER / _PASSWORD and is never
written to a file. Needs the SSH tunnel on 127.0.0.1:5432 (ADR-048). `agent:<id>` runs inside that builder worktree.
Examples:
  python scripts/orchestrator/db_run.py . python -m alembic -c backend/ofo_app/alembic.ini upgrade head
  python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/
Over the tunnel the full app suite takes ~15 min; two timing tests (audit-store advisory-lock mutation, entitlement
post-dated revoke) can fail over the tunnel and pass on rerun and in CI.
"""
import os
import subprocess
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GLOBAL_ENV = os.environ.get("OFO_GLOBAL_ENV", r"D:\Abhay\GLOBAL.env")


def read_env(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def main():
    g = read_env(GLOBAL_ENV)
    p = read_env(os.path.join(ROOT, ".env"))
    admin = ("postgresql" + "+asyncpg://" + g["WINDOWS_VPS_PG_ADMIN_USER"] + ":"
             + urllib.parse.quote(g["WINDOWS_VPS_PG_ADMIN_PASSWORD"], safe="") + "@127.0.0.1:5432/ofo_test")
    env = dict(os.environ, TEST_DATABASE_URL=p["TEST_DATABASE_URL"], TEST_ADMIN_DATABASE_URL=admin,
               ALEMBIC_DATABASE_URL=admin, OFO_REQUIRE_DB_TESTS="1")
    cwd = sys.argv[1]
    if cwd.startswith("agent:"):
        cwd = os.path.join(ROOT, "." + "claude", "worktrees", "agent-" + cwd[6:])
    return subprocess.run(sys.argv[2:], cwd=cwd, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
