"""reset_test_catalogue.py <checkout> [--yes]: empty ONLY ofo_test's catalogue tables, after a verified backup.

Owner-role URL: ALEMBIC_DATABASE_URL if set (db_run.py sets it), else built from GLOBAL.env as db_run.py does;
no secret is printed. The database name must equal exactly "ofo_test" (an allow-list of one), else exit 2 before
any connection. Without --yes it only prints the row counts it would remove. The tables are the allow-list below,
deleted in FK order in ONE transaction; a row outside the allow-list that references one of them refuses the run
(never CASCADE). Before any delete each table is written to <backup dir>/<UTC stamp>/<table>.csv and the files and
row counts are checked. The tool never disables a trigger: the catalogue guards refuse DELETE (SQLSTATE OF006,
migrations 0003/0004); that refusal is reported and the transaction rolls back.
Exit codes: 0 done/dry run, 1 refused or database error, 2 bad database name.
"""
import asyncio
import csv
import datetime
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_run  # (reuse its env reading and GLOBAL.env location)

ALLOWED_DATABASE = "ofo_test"
# Delete order: children first. This tuple is the whole allow-list; no other table name is ever put into a statement.
TABLES = ("catalogue_term_changes", "broker_instruments", "catalogue_contracts")
SCHEMA = "public"
BACKUP_ROOT = r"D:\Abhay\scratch\ofo2-test-db-backups"
EXIT_OK, EXIT_REFUSED, EXIT_BAD_DB = 0, 1, 2
FK_SQL = (
    "SELECT c.conrelid::regclass::text AS child, "
    "ARRAY(SELECT a.attname::text FROM pg_attribute a "
    "WHERE a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)) AS cols "
    "FROM pg_constraint c WHERE c.contype = 'f' AND c.confrelid = $1::regclass"
)


class Refused(Exception):
    pass


def database_name(url):
    """The database a URL names, or None when it names none or carries a query string (which could override it)."""
    parts = urllib.parse.urlsplit(url)
    if parts.query or parts.fragment:
        return None
    name = parts.path[1:] if parts.path.startswith("/") else parts.path
    return name or None


def check_url(url):
    if database_name(url) != ALLOWED_DATABASE:
        raise Refused(f"database must be exactly {ALLOWED_DATABASE!r}; refusing before any connection")


def qualified(table):
    return f'{SCHEMA}."{table}"'


def local_name(regclass_text):
    return regclass_text.replace('"', "").removeprefix(SCHEMA + ".")


def owner_url():
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if url:
        return url
    g = db_run.read_env(db_run.GLOBAL_ENV)
    return ("postgresql://" + g["WINDOWS_VPS_PG_ADMIN_USER"] + ":"
            + urllib.parse.quote(g["WINDOWS_VPS_PG_ADMIN_PASSWORD"], safe="") + "@127.0.0.1:5432/" + ALLOWED_DATABASE)


async def real_connect(url):
    import asyncpg  # noqa: PLC0415  only a real run needs the driver
    return await asyncpg.connect(url.replace("+asyncpg", "", 1))


async def count_rows(conn):
    counts = {}
    for t in TABLES:
        counts[t] = await conn.fetchval(f"SELECT count(*) FROM {qualified(t)}")  # noqa: S608  t is from TABLES
    return counts


async def check_foreign_keys(conn):
    """Refuse when any table outside the allow-list holds a row pointing at an allow-listed table."""
    for parent in TABLES:
        for fk in await conn.fetch(FK_SQL, qualified(parent)):
            child = local_name(fk["child"])
            if child in TABLES:
                continue
            where = " OR ".join('"' + col.replace('"', '""') + '" IS NOT NULL' for col in fk["cols"])
            quoted_child = child.replace(chr(34), chr(34) * 2)
            n = await conn.fetchval(f'SELECT count(*) FROM {SCHEMA}."{quoted_child}" WHERE {where}')  # noqa: S608
            if n:
                raise Refused(f"{child} has {n} row(s) referencing {parent}; nothing deleted")


async def write_backup(conn, counts, folder):
    os.makedirs(folder, exist_ok=False)
    for t in TABLES:
        rows = await conn.fetch(f"SELECT * FROM {qualified(t)}")  # noqa: S608  t is from TABLES
        if len(rows) != counts[t]:
            raise Refused(f"backup of {t}: fetched {len(rows)} row(s), counted {counts[t]}; nothing deleted")
        with open(os.path.join(folder, t + ".csv"), "w", newline="", encoding="utf-8") as f:  # noqa: ASYNC230
            w = csv.writer(f)
            if rows:
                w.writerow(list(rows[0].keys()))
            for r in rows:
                w.writerow(["" if v is None else v for v in r.values()])
    verify_backup(folder, counts)


def verify_backup(folder, counts):
    names = sorted(os.listdir(folder))
    if names != sorted(t + ".csv" for t in TABLES):
        raise Refused(f"backup folder holds {names}, expected one csv per table; nothing deleted")
    for t in TABLES:
        with open(os.path.join(folder, t + ".csv"), newline="", encoding="utf-8") as f:
            written = sum(1 for _ in csv.reader(f))
        written = max(written - 1, 0)  # header line
        if written != counts[t]:
            raise Refused(f"backup of {t} holds {written} row(s), counted {counts[t]}; nothing deleted")


async def run(url, yes, backup_root=BACKUP_ROOT, connect=real_connect, out=print):
    """Returns the exit code. `connect` is only called after the name check passes."""
    try:
        check_url(url)
    except Refused as e:
        out(f"REFUSED: {e}")
        return EXIT_BAD_DB
    try:
        conn = await connect(url)
    except Exception as e:  # noqa: BLE001  any connection failure is reported; nothing was touched
        out(f"CONNECTION FAILED: {type(e).__name__}: {e}")
        return EXIT_REFUSED
    try:
        async with conn.transaction(isolation="repeatable_read"):
            counts = await count_rows(conn)
            for t in TABLES:
                out(f"{t}: {counts[t]} row(s)")
            await check_foreign_keys(conn)
            if not yes:
                out("dry run: nothing deleted (pass --yes to delete)")
                return EXIT_OK
            stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            await write_backup(conn, counts, os.path.join(backup_root, stamp))
            out(f"backup verified in {os.path.join(backup_root, stamp)}")
            for t in TABLES:
                status = await conn.execute(f"DELETE FROM {qualified(t)}")  # noqa: S608  t is from TABLES
                out(f"{t}: {status}")
                if status != f"DELETE {counts[t]}":
                    raise Refused(f"{t}: expected DELETE {counts[t]}, database said {status!r}; rolled back")
        out("done")
        return EXIT_OK
    except Refused as e:
        out(f"REFUSED: {e}")
        return EXIT_REFUSED
    except Exception as e:  # noqa: BLE001  trigger refusal, FK violation, permission denied: rolled back
        out(f"DATABASE ERROR (rolled back, nothing deleted): {type(e).__name__}: {e}")
        return EXIT_REFUSED
    finally:
        await conn.close()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    yes = "--yes" in args
    args = [a for a in args if a != "--yes"]
    if len(args) != 1 or not os.path.isdir(args[0]):
        print(__doc__)
        return EXIT_BAD_DB
    return asyncio.run(run(owner_url(), yes))


if __name__ == "__main__":
    sys.exit(main())
