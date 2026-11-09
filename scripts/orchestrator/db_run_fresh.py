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
import ast
import datetime
import functools
import hashlib
import os
import re
import secrets
import subprocess
import sys
import urllib.parse

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_run  # (reuse its env reading and GLOBAL.env location)

# the optional _f<n> is a per-test-file copy made by tests_app/conftest.py (GC-MERGE1, #649); sweep and drop find it too
NAME_RE = re.compile(r"ofo_test_tmp_[0-9]{14}_[0-9a-f]{4}(_f[0-9]+(_[0-9]+)?)?")
PREFIX = "ofo_test_tmp_"
# template database: <prefix><head revision [a-z0-9_] <=32 chars>_<sha256[:8] of every migration file>; copy source
TPL_PREFIX = "ofo_test_tpl_"
TPL_RE = re.compile(r"ofo_test_tpl_[0-9a-z_]{1,32}_[0-9a-f]{8}")
TPL_READY = "ofo_tpl_ready "  # COMMENT ON DATABASE marker + STAMP; usable template
TPL_BUILDING = "ofo_tpl_building "  # set right after CREATE: a half-built template, aged by its stamp
LOCK_WAIT = 600  # seconds to wait for the advisory lock before falling back to the full migration path
LOCK_POLL = 2
DB_PRIVS = "CONNECT, CREATE, TEMPORARY"  # revoked from PUBLIC on a copy: 0001 revokes CREATE, TEMPORARY; CI CONNECT
SEED_FILES = (os.path.join("backend", "ofo", "adjustment", "system_playbooks.json"),)  # read by migration 0031
TPL_LOCK_KEY = 7406120911  # fixed pg_advisory_lock key: one build-or-copy at a time
VERSIONS = os.path.join("backend", "ofo_app", "alembic", "versions")
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


def is_template_name(name):
    return isinstance(name, str) and TPL_RE.fullmatch(name) is not None


def _module_files(backend, module):
    """The .py files a dotted module name `ofo...` / `ofo_app...` resolves to under backend/ (its package inits too)."""
    parts = module.split(".")
    if parts[0] not in ("ofo", "ofo_app"):
        return []
    out = []
    for k in range(1, len(parts) + 1):
        base = os.path.join(backend, *parts[:k])
        out.extend(f for f in (base + ".py", os.path.join(base, "__init__.py")) if os.path.isfile(f))
    return out


def input_files(checkout):
    """Every file the upgrade reads: all of versions/ (and env.py), the seed files, and the project modules the
    migrations import, transitively (ast, no import is executed)."""
    backend = os.path.join(checkout, "backend")
    d = os.path.join(checkout, VERSIONS)
    found = {os.path.join(d, f) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}
    found.add(os.path.join(os.path.dirname(d), "env.py"))
    found.update(os.path.join(checkout, f) for f in SEED_FILES)
    todo = [f for f in sorted(found) if f.endswith(".py") and os.path.isfile(f)]
    while todo:
        with open(todo.pop(), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            mods = ([a.name for a in node.names] if isinstance(node, ast.Import) else
                    [node.module] + [f"{node.module}.{a.name}" for a in node.names]
                    if isinstance(node, ast.ImportFrom) and node.module and not node.level else [])
            for m in mods:
                for f in _module_files(backend, m):
                    if f not in found:
                        found.add(f)
                        todo.append(f)
    return sorted(f for f in found if os.path.isfile(f))


def template_name(checkout):
    """Head revision + hash of every input of the upgrade (see input_files) and the app role name, so any change that
    could change the migrated schema names a new template."""
    d = os.path.join(checkout, VERSIONS)
    h, revs, downs = hashlib.sha256(), set(), set()
    h.update(os.environ.get("OFO_APP_DB_ROLE", "ofo_app").encode() + b"\0")
    for f in input_files(checkout):
        with open(f, "rb") as fh:
            raw = fh.read()
        h.update(os.path.relpath(f, checkout).replace(os.sep, "/").encode() + b"\0" + raw + b"\0")
        if os.path.dirname(f) == d and f.endswith(".py"):
            for line in raw.decode("utf-8").splitlines():
                if line.startswith(("revision", "down_revision")):
                    (downs if line.startswith("down") else revs).update(re.findall(r"[\"']([^\"']+)[\"']", line))
    heads = sorted(revs - downs)
    if len(heads) != 1:
        raise ValueError(f"cannot find a single alembic head in {d}: {heads}")
    return f"{TPL_PREFIX}{re.sub('[^0-9a-z]', '_', heads[0].lower())[:32]}_{h.hexdigest()[:8]}"


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
    if not (is_tool_name(name) or is_template_name(name)):
        raise Refused(f"refusing to drop {name!r}: not a name made by this tool")
    await conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1 AND pid <> pg_backend_pid()", name)
    await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')


async def drop_with_copies(conn, name):
    """Drop the per-test-file copies of `name` a killed pytest left behind, then `name` itself (allow-list on each)."""
    rows = await conn.fetch("SELECT datname FROM pg_database WHERE starts_with(datname, $1)", name + "_f")
    for r in rows:
        await drop_database(conn, r["datname"])
    await drop_database(conn, name)


async def copy_database(conn, name, template, on_created=None):
    """CREATE `name` as a server-side copy of `template`, then the same grants as create_database."""
    if not (is_tool_name(name) and is_template_name(template)):
        raise Refused(f"refusing to copy {template!r} to {name!r}")
    await conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    if on_created is not None:
        on_created()
    # a template does not copy database-level grants: re-apply what a migrated database has (as tests_app/conftest.py)
    await conn.execute(f'REVOKE {DB_PRIVS} ON DATABASE "{name}" FROM PUBLIC')
    await conn.execute(f'GRANT CONNECT ON DATABASE "{name}" TO {APP_ROLE}')


async def create_database(conn, name, on_created=None):
    """CREATE, then the grants; `on_created` is called right after the CREATE succeeds, so a CREATE that failed (e.g.
    the name already exists: another run's database) is never dropped by this run."""
    if not (is_tool_name(name) or is_template_name(name)):
        raise Refused(f"refusing to create {name!r}")
    await conn.execute(f'CREATE DATABASE "{name}"')
    if on_created is not None:
        on_created()
    await conn.execute(f'REVOKE CONNECT ON DATABASE "{name}" FROM PUBLIC')
    await conn.execute(f'GRANT CONNECT ON DATABASE "{name}" TO {APP_ROLE}')


def _comment_time(comment):
    """The UTC stamp of a ready/building marker comment, or None (no marker, or unparseable)."""
    for prefix in (TPL_READY, TPL_BUILDING):
        if comment.startswith(prefix):
            try:
                return datetime.datetime.strptime(comment[len(prefix):], STAMP).replace(tzinfo=datetime.UTC)
            except ValueError:
                return None
    return None


async def sweep_templates(conn, keep, now, out):
    """Drop template databases (ready or half-built) whose marker stamp is older than SWEEP_AGE. Never `keep` (the
    current key); `keep` None = keep every template. No parsable marker: kept."""
    rows = await conn.fetch("SELECT datname, shobj_description(oid, 'pg_database') AS comment FROM pg_database "
                            "WHERE datname LIKE 'ofo\\_test\\_tpl\\_%'")
    dropped = []
    for r in sorted(rows, key=lambda r: r["datname"]):
        n, t = r["datname"], _comment_time(r.get("comment") or "")
        if not is_template_name(n) or keep is None or n == keep or t is None or now - t < SWEEP_AGE:
            out(f"sweep: {n} kept")
            continue
        await drop_database(conn, n)
        out(f"sweep: dropped {n}")
        dropped.append(n)
    return dropped


async def sweep(conn, now=None, out=print, keep_template=None):
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
    return old + await sweep_templates(conn, keep_template, now, out)


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

    use_template = True  # tests switch it off per instance

    def __init__(self, settings, connect, runner=subprocess.run, name=None, err=None):
        self.admin, self.app_url, self.secrets = settings
        self.connect = connect
        self.runner = runner
        self.err = err or functools.partial(print, file=sys.stderr)
        self.name = name or make_name()
        self.created = False
        tmp_admin = with_database(self.admin, self.name)
        self.env = dict(os.environ, TEST_DATABASE_URL=with_database(self.app_url, self.name),
                        TEST_ADMIN_DATABASE_URL=tmp_admin, ALEMBIC_DATABASE_URL=tmp_admin, OFO_REQUIRE_DB_TESTS="1")

    def _mark_created(self):
        self.created = True

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
            # Drop only what THIS run created (the CREATE succeeded, even if a grant then failed); a CREATE that
            # failed - e.g. the name exists because another run picked it - is never dropped here.
            # The allow-list is in drop_database.
            if self.created:
                code = self._drop_own(code)
        return code

    def _drop_own(self, code):
        try:
            self._admin_do(drop_with_copies)
        except Exception as e:  # noqa: BLE001 - any server answer is reported with its step
            detail = f"{type(e).__name__}: {scrub(e, self.secrets)}"
            self.err(f"db_run_fresh: step drop failed for {self.name}: {detail}")
            self.err("db_run_fresh: run --sweep later to remove it")
            return code or EXIT_SETUP
        return code

    async def _copy_from_template(self, conn, checkout):
        """Under the advisory lock: build the template if it has no ready marker, then copy it to this run's name."""
        tpl = template_name(checkout)
        waited = 0
        while not await conn.fetchval("SELECT pg_try_advisory_lock($1)", TPL_LOCK_KEY):
            if waited >= LOCK_WAIT:
                raise TimeoutError(f"template lock not free after {LOCK_WAIT} s")
            await asyncio.sleep(LOCK_POLL)
            waited += LOCK_POLL
        try:
            marker = await conn.fetchval(
                "SELECT shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = $1", tpl)
            if not (marker or "").startswith(TPL_READY):
                await drop_database(conn, tpl)  # missing or half built; we hold the lock, nobody else builds
                await create_database(conn, tpl)
                building = datetime.datetime.now(datetime.UTC).strftime(STAMP)
                await conn.execute(f'COMMENT ON DATABASE "{tpl}" IS \'{TPL_BUILDING}{building}\'')
                tpl_url = with_database(self.admin, tpl)
                res = self.runner(ALEMBIC, cwd=checkout, env=dict(self.env, ALEMBIC_DATABASE_URL=tpl_url),
                                  capture_output=True, text=True)
                if res.returncode != 0:
                    await drop_database(conn, tpl)
                    raise RuntimeError("template migrate failed: " + scrub(res.stderr or "", self.secrets)[-300:])
                stamp = datetime.datetime.now(datetime.UTC).strftime(STAMP)
                await conn.execute(f'COMMENT ON DATABASE "{tpl}" IS \'{TPL_READY}{stamp}\'')
            await copy_database(conn, self.name, tpl, on_created=self._mark_created)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", TPL_LOCK_KEY)

    def _try_template(self, checkout):
        """True when self.name is a ready copy. Any template error is logged, this run's database dropped, and False
        returned so the caller falls back to the full migration path."""
        if not self.use_template:
            return False
        try:
            asyncio.run(_connect_and(self.connect, self.admin, lambda c: self._copy_from_template(c, checkout)))
            return True
        except Exception as e:  # noqa: BLE001 - never fail a run because of the template
            self.err(f"db_run_fresh: template unavailable, full migration instead: {type(e).__name__}: "
                     f"{scrub(e, self.secrets)}")
            if self.created:
                self._drop_own(0)
                self.created = False
            return False

    def _setup_and_run(self, checkout, command):
        step = "create"
        try:
            if self._try_template(checkout):
                return self.runner(command, cwd=checkout, env=self.env).returncode
            self._admin_do(functools.partial(create_database, on_created=self._mark_created))
            step = "migrate"
            res = self.runner(ALEMBIC, cwd=checkout, env=self.env, capture_output=True, text=True)
            if res.returncode != 0:  # scrub BEFORE cutting, so a secret split by the cut can never show
                self.err("db_run_fresh: step migrate failed: " + scrub(res.stderr or "", self.secrets)[-600:])
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
        try:
            keep = template_name(db_run.ROOT)
        except (ValueError, OSError, SyntaxError) as e:  # no single head: sweep tmp, keep templates
            print(f"db_run_fresh: sweep keeps every template: {e}", file=sys.stderr)
            keep = None
        return _guarded(_Action(connect, functools.partial(sweep, keep_template=keep)), settings, "sweep")
    if len(argv) == MIN_ARGS and argv[0] == "--drop":  # the allow-list runs inside drop_database, before any DROP
        t = name_time(argv[1])
        if t is not None and datetime.datetime.now(datetime.UTC) - t < SWEEP_AGE:
            print(f"db_run_fresh: refusing to drop {argv[1]!r}: younger than {SWEEP_AGE} "
                  "(another run may be using it)", file=sys.stderr)
            return EXIT_REFUSED
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
