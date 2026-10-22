"""db_run_fresh.py <checkout> <command...> | --sweep: run a command against a throwaway, freshly migrated database.

Creates ofo_test_tmp_<UTC yyyymmddhhmmss>_<4 hex> as the owner role, grants the limited ofo_app role what CI grants,
migrates it to head as the owner, runs the command with TEST_DATABASE_URL (ofo_app) / TEST_ADMIN_DATABASE_URL /
ALEMBIC_DATABASE_URL pointing at it, and always drops it. A database is dropped only when its name matches the exact
allow-list pattern below (this tool made it); anything else is refused (exit 2). Prints no password or URL.
Exit codes: the command's own code; 2 = drop refused / bad usage; 3 = a setup step failed (step named on stderr).
`--sweep` lists, then drops, leftover tool-made databases older than 24 h (after a crash).
Example (issue #497, empty catalogue):
  python scripts/orchestrator/db_run_fresh.py . python -m pytest -q -p no:cacheprovider -c pytest-app.ini \
      tests_app/test_catalogue_refresh.py
"""
import asyncio
import datetime
import functools
import os
import re
import secrets
import subprocess
import sys
import urllib.parse

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_run  # (reuse its env reading and GLOBAL.env location)

NAME_RE = re.compile(r"ofo_test_tmp_[0-9]{14}_[0-9a-f]{4}")
PREFIX = "ofo_test_tmp_"
SWEEP_AGE = datetime.timedelta(hours=24)
APP_ROLE = "ofo_app"
EXIT_REFUSED = 2
EXIT_SETUP = 3
STAMP = "%Y%m%d%H%M%S"
ALEMBIC = ["python", "-m", "alembic", "-c", "backend/ofo_app/alembic.ini", "upgrade", "head"]
MIN_ARGS = 2


class Refused(Exception):
    pass


def is_tool_name(name):
    """Exact match, fail closed: only a name this tool could have made."""
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


def make_name(now=None, rand=None):
    now = now or datetime.datetime.now(datetime.UTC)
    return f"{PREFIX}{now.strftime(STAMP)}_{rand or secrets.token_hex(2)}"


def name_time(name):
    """The UTC creation time encoded in a tool name, or None when it does not parse."""
    if not is_tool_name(name):
        return None
    try:
        return datetime.datetime.strptime(name[len(PREFIX):][:14], STAMP).replace(tzinfo=datetime.UTC)
    except ValueError:
        return None


def scrub(text, secret_list):
    text = str(text)
    for s in secret_list:
        if s:
            text = text.replace(s, "***").replace(urllib.parse.quote(s, safe=""), "***")
    return text


async def drop_database(conn, name):
    """Drop `name` only if the allow-list accepts it; terminate that database's own connections first."""
    if not is_tool_name(name):
        raise Refused(f"refusing to drop {name!r}: not a name made by this tool")
    await conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()", name)
    await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


async def create_database(conn, name):
    if not is_tool_name(name):
        raise Refused(f"refusing to create {name!r}")
    await conn.execute(f'CREATE DATABASE "{name}"')
    await conn.execute(f'REVOKE CONNECT ON DATABASE "{name}" FROM PUBLIC')
    await conn.execute(f'GRANT CONNECT ON DATABASE "{name}" TO {APP_ROLE}')


async def sweep(conn, now=None, out=print):
    now = now or datetime.datetime.now(datetime.UTC)
    rows = await conn.fetch("SELECT datname FROM pg_database WHERE datname LIKE 'ofo\\_test\\_tmp\\_%'")
    old = []
    for n in sorted(r["datname"] for r in rows):
        t = name_time(n)
        keep = t is None or now - t < SWEEP_AGE
        out(f"sweep: {n} {'kept' if keep else 'will drop'}")
        if not keep:
            old.append(n)
    for n in old:
        await drop_database(conn, n)
        out(f"sweep: dropped {n}")
    return old


def with_database(url, name):
    parts = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(parts._replace(path="/" + name))


def load_settings():
    g = db_run.read_env(db_run.GLOBAL_ENV)
    p = db_run.read_env(os.path.join(db_run.ROOT, ".env"))
    admin = ("postgresql" + "+asyncpg://" + g["WINDOWS_VPS_PG_ADMIN_USER"] + ":"
             + urllib.parse.quote(g["WINDOWS_VPS_PG_ADMIN_PASSWORD"], safe="") + "@127.0.0.1:5432/ofo_test")
    return admin, p["TEST_DATABASE_URL"], [g["WINDOWS_VPS_PG_ADMIN_PASSWORD"],
                                           urllib.parse.urlsplit(p["TEST_DATABASE_URL"]).password]


async def real_connect(url):
    return await asyncpg.connect(url.replace("+asyncpg", "", 1))


async def _connect_and(connect, url, action):
    conn = await connect(url)
    try:
        return await action(conn)
    finally:
        await conn.close()


class Fresh:
    """One run: its own database name, the owner URL, the fakes-able connect and runner."""

    def __init__(self, settings, connect, runner=subprocess.run, name=None, err=None):
        self.admin, self.app_url, self.secrets = settings
        self.connect = connect
        self.runner = runner
        self.err = err or functools.partial(print, file=sys.stderr)
        self.name = name or make_name()
        tmp_admin = with_database(self.admin, self.name)
        self.env = dict(os.environ, TEST_DATABASE_URL=with_database(self.app_url, self.name),
                        TEST_ADMIN_DATABASE_URL=tmp_admin, ALEMBIC_DATABASE_URL=tmp_admin, OFO_REQUIRE_DB_TESTS="1")

    def _admin_do(self, action):
        asyncio.run(_connect_and(self.connect, self.admin, functools.partial(action, name=self.name)))

    def run(self, checkout, command):
        """Returns the exit code. The drop in the finally runs on every path (failure, interrupt)."""
        if urllib.parse.urlsplit(self.app_url).username != APP_ROLE:
            self.err(f"db_run_fresh: step app-url failed: TEST_DATABASE_URL is not the {APP_ROLE} role")
            return EXIT_SETUP
        code = EXIT_SETUP
        try:
            code = self._setup_and_run(checkout, command)
        finally:
            # CREATE may have half-succeeded (database made, grant refused), so the drop always runs; IF EXISTS keeps a
            # CREATE that never happened quiet. Only this run's own name is ever dropped (allow-list in drop_database).
            try:
                self._admin_do(drop_database)
            except Exception as e:  # noqa: BLE001 - any server answer is reported with its step
                detail = f"{type(e).__name__}: {scrub(e, self.secrets)}"
                self.err(f"db_run_fresh: step drop failed for {self.name}: {detail}")
                self.err("db_run_fresh: run --sweep later to remove it")
                code = code or EXIT_SETUP
        return code

    def _setup_and_run(self, checkout, command):
        step = "create"
        try:
            self._admin_do(create_database)
            step = "migrate"
            res = self.runner(ALEMBIC, cwd=checkout, env=self.env, capture_output=True, text=True)
            if res.returncode != 0:
                self.err("db_run_fresh: step migrate failed: " + scrub((res.stderr or "")[-600:], self.secrets))
                return EXIT_SETUP
        except Exception as e:  # noqa: BLE001 - server answers (no privilege, name clash, ...) are reported with a step
            self.err(f"db_run_fresh: step {step} failed: {type(e).__name__}: {scrub(e, self.secrets)}")
            return EXIT_SETUP
        return self.runner(command, cwd=checkout, env=self.env).returncode


def _guarded(coro_fn, settings, step):
    """Run one owner-role action; returns an exit code. A Refused (allow-list) is exit 2, a server answer exit 3."""
    try:
        asyncio.run(_connect_and(coro_fn.connect, settings[0], coro_fn.action))
    except Refused as e:
        print(f"db_run_fresh: {e}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as e:  # noqa: BLE001 - reported with its step
        print(f"db_run_fresh: step {step} failed: {type(e).__name__}: {scrub(e, settings[2])}", file=sys.stderr)
        return EXIT_SETUP
    return 0


class _Action:
    def __init__(self, connect, action):
        self.connect, self.action = connect, action


def main(argv=None, connect=real_connect, settings_loader=load_settings, runner=subprocess.run):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--sweep"]:
        settings = settings_loader()
        return _guarded(_Action(connect, sweep), settings, "sweep")
    if len(argv) == MIN_ARGS and argv[0] == "--drop":  # the allow-list runs inside drop_database, before any DROP
        settings = settings_loader()
        return _guarded(_Action(connect, functools.partial(drop_database, name=argv[1])), settings, "drop")
    if len(argv) < MIN_ARGS or argv[0].startswith("--"):
        print("usage: db_run_fresh.py <checkout> <command...> | --sweep | --drop <name>", file=sys.stderr)
        return EXIT_REFUSED
    try:
        return Fresh(settings_loader(), connect, runner).run(argv[0], argv[1:])
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
