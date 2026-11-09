"""db_run_fresh.py with a fake connection and a fake runner: no real database is ever created or dropped."""
import asyncio
import datetime
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

# db_run_fresh imports asyncpg, an app-only package: the kit tests job installs only pyyaml, jsonschema and pytest, so
# there this file is skipped at collection (the app job and local runs, which have asyncpg, run it).
pytest.importorskip("asyncpg")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import db_run_fresh as fresh

SECRET = "fake/secret:word"  # a made-up owner password; URLs are assembled at runtime
APP_SECRET = "fake-app-word"
HOSTDB = "@127.0.0.1:5432/ofo_test"
SCHEME = "postgresql" + "+asyncpg://"
ADMIN = SCHEME + "owner:" + urllib.parse.quote(SECRET, safe="") + HOSTDB
APP = SCHEME + "ofo_app:" + APP_SECRET + HOSTDB
SETTINGS = (ADMIN, APP, [SECRET, APP_SECRET])
GOOD = "ofo_test_tmp_20261022101500_ab12"
REFUSED, SETUP, INTERRUPT, CMD_RC = 2, 3, 130, 7
NOW = datetime.datetime(2026, 10, 22, 12, 0, 0, tzinfo=datetime.UTC)
FULLWIDTH = "ofo_test_tmp_" + "".join(chr(0xFF10 + int(d)) for d in "20261022101500") + "_ab12"
BAD_NAMES = ["ofo_test", "ofo_dev", "ipodhan", "postgres", "ofo_test_tmp_x", "ofo_test_tmp_20261022000000_zzzz",
             'ofo_test_tmp_20261022101500_ab12"; DROP DATABASE ofo_test; --', "ofo_test tmp", "",
             GOOD + "\n", " " + GOOD, GOOD.upper(), GOOD + "3", FULLWIDTH]


class FakeConn:
    def __init__(self, log, fail_on=None, rows=()):
        self.log, self.fail_on, self.rows = log, fail_on, rows

    async def execute(self, sql, *args):
        self.log.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError(f"server said no using {SECRET}")

    async def fetch(self, sql, *args):
        self.log.append(sql)
        return [{"datname": n} for n in self.rows]

    async def close(self):
        self.log.append("close")


def make_connect(log, **kw):
    async def connect(url):
        log.append(("connect", url))
        return FakeConn(log, **kw)
    return connect


class Runner:
    def __init__(self, migrate_rc=0, command_rc=0, raise_on_command=None):
        self.calls, self.migrate_rc, self.command_rc = [], migrate_rc, command_rc
        self.raise_on_command = raise_on_command

    def __call__(self, argv, **kw):
        self.calls.append((argv, kw))
        if argv == fresh.ALEMBIC:
            return subprocess.CompletedProcess(argv, self.migrate_rc, "", f"boom {SECRET}" if self.migrate_rc else "")
        if self.raise_on_command:
            raise self.raise_on_command
        return subprocess.CompletedProcess(argv, self.command_rc)


def sql(log):
    return [x for x in log if isinstance(x, str)]


def drops(log):
    return [x for x in sql(log) if x.startswith("DROP")]


def go(log, runner, **kw):
    errs = []
    fr = fresh.Fresh(SETTINGS, make_connect(log, **kw), runner, name="ofo_test_tmp_20261022120000_ab12", err=errs.append)
    fr.use_template = False
    code = fr.run(".", ["cmd"])
    return code, errs


@pytest.mark.parametrize("name", BAD_NAMES)
def test_drop_refuses_any_name_not_made_by_the_tool(name):
    log = []
    code = fresh.main(["--drop", name], connect=make_connect(log), settings_loader=lambda: SETTINGS)
    assert code == REFUSED
    assert drops(log) == [] and not any("pg_terminate" in s for s in sql(log))


OLD_GOOD = "ofo_test_tmp_20200101000000_ab12"  # older than the 24 h sweep age


def test_drop_accepts_an_old_tool_name_and_terminates_only_its_connections():
    log = []
    assert fresh.main(["--drop", OLD_GOOD], connect=make_connect(log), settings_loader=lambda: SETTINGS) == 0
    assert drops(log) == [f'DROP DATABASE IF EXISTS "{OLD_GOOD}"']
    assert any("datname = $1" in s for s in sql(log))


def test_drop_refuses_a_tool_name_younger_than_the_sweep_age(capsys):
    """Review 2026-10-22: --drop must not kill another session's run that is still going."""
    log = []
    young = "ofo_test_tmp_" + fresh.datetime.datetime.now(fresh.datetime.UTC).strftime("%Y%m%d%H%M%S") + "_ab12"
    assert fresh.main(["--drop", young], connect=make_connect(log), settings_loader=lambda: SETTINGS) == 2
    assert drops(log) == []
    assert "younger than" in capsys.readouterr().err


def test_dropped_when_command_fails_and_exit_code_is_the_commands():
    log = []
    code, _ = go(log, Runner(command_rc=7))
    assert code == CMD_RC
    assert len(drops(log)) == 1


def test_dropped_when_migration_fails_exit_3_with_step_named():
    log, runner = [], Runner(migrate_rc=1)
    code, errs = go(log, runner)
    assert code == SETUP and any("step migrate failed" in e for e in errs)
    assert len(drops(log)) == 1
    assert len(runner.calls) == 1  # the command never ran


def test_dropped_on_keyboard_interrupt():
    log = []
    with pytest.raises(KeyboardInterrupt):
        go(log, Runner(raise_on_command=KeyboardInterrupt()))
    assert len(drops(log)) == 1


def test_main_maps_interrupt_to_130():
    log = []
    runner = Runner(raise_on_command=KeyboardInterrupt())
    code = fresh.main([".", "cmd"], connect=make_connect(log), settings_loader=lambda: SETTINGS, runner=runner)
    assert code == INTERRUPT and len(drops(log)) == 1


def test_create_refused_exit_3_and_nothing_dropped():
    """Review 2026-10-22: a failed CREATE (the name exists: another run's database) is never dropped by this run."""
    log, runner = [], Runner()
    code, errs = go(log, runner, fail_on="CREATE DATABASE")
    assert code == SETUP and any("step create failed" in e for e in errs)
    assert runner.calls == []
    assert drops(log) == []


def test_grant_refused_after_create_still_drops_own_database():
    """The CREATE succeeded, then a grant failed: this run made the database, so it drops it."""
    log, runner = [], Runner()
    code, _ = go(log, runner, fail_on="GRANT CONNECT")
    assert code == SETUP and runner.calls == []
    assert len(drops(log)) == 1 and drops(log)[0].startswith('DROP DATABASE IF EXISTS "ofo_test_tmp_')


def test_drop_failure_reported_with_step_and_nonzero_exit():
    code, errs = go([], Runner(), fail_on="DROP DATABASE")
    assert code == SETUP and any("step drop failed" in e for e in errs)


def test_command_sees_app_role_and_temp_database_never_the_owner():
    runner = Runner()
    code, _ = go([], runner)
    assert code == 0
    env = runner.calls[-1][1]["env"]
    app_url = env["TEST_DATABASE_URL"]
    assert urllib.parse.urlsplit(app_url).username == "ofo_app"
    assert app_url.endswith("/ofo_test_tmp_20261022120000_ab12") and "owner" not in app_url
    assert not app_url.endswith("/ofo_test")
    assert urllib.parse.urlsplit(env["TEST_ADMIN_DATABASE_URL"]).path == urllib.parse.urlsplit(app_url).path
    assert urllib.parse.urlsplit(env["ALEMBIC_DATABASE_URL"]).path == urllib.parse.urlsplit(app_url).path
    migrate_env = runner.calls[0][1]["env"]
    assert urllib.parse.urlsplit(migrate_env["ALEMBIC_DATABASE_URL"]).path == "/ofo_test_tmp_20261022120000_ab12"


def test_non_app_role_in_test_database_url_is_refused_before_any_connection():
    log, errs = [], []
    code = fresh.Fresh((ADMIN, ADMIN, [SECRET]), make_connect(log), Runner(), err=errs.append).run(".", ["cmd"])
    assert code == SETUP and log == [] and any("app-url" in e for e in errs)


def test_grants_match_ci():
    log = []
    go(log, Runner())
    s = sql(log)
    assert any(x.startswith("REVOKE CONNECT ON DATABASE") and x.endswith("FROM PUBLIC") for x in s)
    assert any(x.startswith("GRANT CONNECT ON DATABASE") and x.endswith("TO ofo_app") for x in s)


def test_sweep_drops_only_old_pattern_names():
    old, young = "ofo_test_tmp_20261020000000_aaaa", "ofo_test_tmp_20261022110000_bbbb"
    log, out = [], []
    rows = [old, young, "ofo_test_tmp_x", "ofo_test", "ofo_test_tmp_20261020000000_AAAA"]
    dropped = asyncio.run(fresh.sweep(FakeConn(log, rows=rows), now=NOW, out=out.append))
    assert dropped == [old]
    assert drops(log) == [f'DROP DATABASE IF EXISTS "{old}"']
    assert any(young in o and "kept" in o for o in out)
    assert any("will drop" in o for o in out)


def test_sweep_keeps_future_dated_and_unparseable_dates():
    log = []
    rows = ["ofo_test_tmp_20271022000000_aaaa", "ofo_test_tmp_20269999999999_bbbb"]
    assert asyncio.run(fresh.sweep(FakeConn(log, rows=rows), now=NOW, out=lambda _m: None)) == []
    assert drops(log) == []


def test_output_never_contains_the_password(capsys):
    log = []
    for kw, runner in (({"fail_on": "CREATE DATABASE"}, Runner()), ({}, Runner(migrate_rc=1)),
                       ({"fail_on": "DROP DATABASE"}, Runner())):
        fresh.main([".", "cmd"], connect=make_connect(log, **kw), settings_loader=lambda: SETTINGS, runner=runner)
    fresh.main(["--drop", "ofo_test"], connect=make_connect(log), settings_loader=lambda: SETTINGS)
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "db_run_fresh: step" in text
    for leaked in (SECRET, "fake/secret", urllib.parse.quote(SECRET, safe=""), APP_SECRET, "postgresql"):
        assert leaked not in text


def test_name_is_unique_per_run_in_the_same_second():
    names = {fresh.make_name(NOW) for _ in range(20)}
    assert len(names) > 1
    assert all(fresh.is_tool_name(n) for n in names)


def test_usage_error_exits_2():
    assert fresh.main(["."], settings_loader=lambda: SETTINGS) == REFUSED
    assert fresh.main(["--bogus", "x"], settings_loader=lambda: SETTINGS) == REFUSED


def test_sweep_finds_the_per_file_copies_of_an_old_run():
    """GC-MERGE1 (#649): tests_app/conftest.py copies the run's database per test file as <name>_f<n>; a killed run
    leaves them, and --sweep must drop them like their parent. A suffix that is not _f<digits> stays refused."""
    old = "ofo_test_tmp_20261020000000_aaaa"
    log = []
    rows = [old, old + "_f1", old + "_f12", old + "_fx", old + "_g1"]
    dropped = asyncio.run(fresh.sweep(FakeConn(log, rows=rows), now=NOW, out=lambda _m: None))
    assert dropped == [old, old + "_f1", old + "_f12"]
    assert not fresh.is_tool_name("ofo_test_f1")
    assert not fresh.is_tool_name(old + "_f")


def test_pid_style_copy_names_are_tool_names():
    old = "ofo_test_tmp_20261020000000_aaaa"
    assert fresh.is_tool_name(old + "_f4242_3") and fresh.is_tool_name(old + "_f7")
    for bad in ("ofo_test_f1", "ofo_dev", "ofo_test", old + "_f4242_", old + "_f_3", old + "_f1_2_3"):
        assert not fresh.is_tool_name(bad)


def test_drop_with_copies_drops_the_copies_before_the_parent():
    old = "ofo_test_tmp_20261020000000_aaaa"
    log = []
    asyncio.run(fresh.drop_with_copies(FakeConn(log, rows=[old + "_f1", old + "_f2"]), old))
    assert drops(log) == [f'DROP DATABASE IF EXISTS "{n}"' for n in (old + "_f1", old + "_f2", old)]


# ---- template database (copy instead of replaying every migration) ----
TPL = "ofo_test_tpl_0048_ic_t11c_t20b_built_0123abcd"


class TplConn(FakeConn):
    """fetchval answers the ready-marker lookup: None = template missing/half built, a string = ready."""

    def __init__(self, log, marker=None, **kw):
        super().__init__(log, **kw)
        self.marker = marker

    async def fetchval(self, sql, *args):
        self.log.append(sql)
        return self.marker

    async def fetch(self, sql, *args):
        self.log.append(sql)
        return self.rows


def tpl_go(log, runner, marker=None, **kw):
    errs = []

    async def connect(url):
        log.append(("connect", url))
        return TplConn(log, marker=marker, **kw)
    fr = fresh.Fresh(SETTINGS, connect, runner, name="ofo_test_tmp_20261022120000_ab12", err=errs.append)
    fresh.template_name = lambda _c: TPL
    return fr.run(".", ["cmd"]), errs


@pytest.fixture(autouse=True)
def _restore_template_name():
    orig = fresh.template_name
    yield
    fresh.template_name = orig


def fake_versions(tmp_path, extra=""):
    d = tmp_path / fresh.VERSIONS
    d.mkdir(parents=True)
    (d / "0001_a.py").write_text("revision = '0001_a'\ndown_revision = None\n")
    (d / "0002_b.py").write_text("revision = '0002_b'\ndown_revision = '0001_a'\n" + extra)
    return str(tmp_path)


def test_template_name_is_head_plus_hash_and_changes_with_any_migration_change(tmp_path):
    n1 = fresh.template_name(fake_versions(tmp_path))
    assert n1.startswith("ofo_test_tpl_0002_b_") and fresh.is_template_name(n1)
    (tmp_path / fresh.VERSIONS / "0001_a.py").write_text("revision = '0001_a'\ndown_revision = None\n# edit\n")
    n2 = fresh.template_name(str(tmp_path))
    assert n2 != n1 and n2.startswith("ofo_test_tpl_0002_b_")


def test_real_migrations_give_a_valid_template_name():
    assert fresh.is_template_name(fresh.template_name(str(Path(__file__).resolve().parents[2])))


@pytest.mark.parametrize("name", ["ofo_test", "ofo_dev", "ipodhan_prod", "postgres", "algochanakya",
                                  "ofo_test_tpl_", "ofo_test_tpl_x", TPL + "x", TPL.upper(),
                                  TPL + '"; DROP DATABASE ofo_test; --'])
def test_guard_refuses_every_other_database_even_with_the_template_path(name):
    assert not fresh.is_template_name(name) and not fresh.is_tool_name(name)
    log = []
    for coro in (fresh.drop_database(FakeConn(log), name), fresh.create_database(FakeConn(log), name),
                 fresh.copy_database(FakeConn(log), name, TPL), fresh.copy_database(FakeConn(log), GOOD, name)):
        with pytest.raises(fresh.Refused):
            asyncio.run(coro)
    assert sql(log) == []


def test_guard_accepts_tmp_and_template_names():
    log = []
    asyncio.run(fresh.drop_database(FakeConn(log), TPL))
    asyncio.run(fresh.drop_database(FakeConn(log), GOOD))
    asyncio.run(fresh.copy_database(FakeConn(log), GOOD, TPL))
    assert f'CREATE DATABASE "{GOOD}" TEMPLATE "{TPL}"' in sql(log)


def test_ready_template_is_copied_without_migrating():
    log, runner = [], Runner()
    code, errs = tpl_go(log, runner, marker="ofo_tpl_ready 20261022100000")
    assert code == 0 and errs == []
    assert any(s.startswith("CREATE DATABASE") and f'TEMPLATE "{TPL}"' in s for s in sql(log))
    assert [c[0] for c in runner.calls] == [["cmd"]]  # no alembic run
    assert len(drops(log)) == 1 and TPL not in drops(log)[0]  # only the run's own database is dropped
    s = sql(log)
    copy = s.index(next(x for x in s if "TEMPLATE" in x))
    assert s.index("SELECT pg_advisory_lock($1)") < copy < s.index("SELECT pg_advisory_unlock($1)")


def test_missing_template_is_built_marked_then_copied():
    log, runner = [], Runner()
    code, _ = tpl_go(log, runner)
    assert code == 0
    assert [c[0] for c in runner.calls] == [fresh.ALEMBIC, ["cmd"]]
    assert runner.calls[0][1]["env"]["ALEMBIC_DATABASE_URL"].endswith("/" + TPL)
    s = sql(log)
    assert any(x.startswith(f'COMMENT ON DATABASE "{TPL}" IS') for x in s)
    comment = s.index(next(x for x in s if x.startswith("COMMENT")))
    assert s.index(f'CREATE DATABASE "{TPL}"') < comment < s.index(next(x for x in s if "TEMPLATE" in x))


def test_template_error_falls_back_to_full_migration_and_run_still_succeeds():
    log, runner = [], Runner()
    code, errs = tpl_go(log, runner, marker="ofo_tpl_ready 20261022100000", fail_on="TEMPLATE")
    assert code == 0 and any("template unavailable" in e for e in errs)
    assert [c[0] for c in runner.calls] == [fresh.ALEMBIC, ["cmd"]]  # today's path ran
    assert all(SECRET not in e for e in errs)


def test_template_migrate_failure_drops_the_half_built_template_and_falls_back():
    log, runner = [], Runner(migrate_rc=1)
    code, errs = tpl_go(log, runner)
    assert code == SETUP and any("template unavailable" in e for e in errs)
    assert f'DROP DATABASE IF EXISTS "{TPL}"' in sql(log)


def test_sweep_drops_stale_templates_and_keeps_the_current_one():
    stale, cur = "ofo_test_tpl_0047_x_aaaaaaaa", TPL
    rows = [{"datname": stale, "comment": "ofo_tpl_ready 20261020000000"},
            {"datname": cur, "comment": "ofo_tpl_ready 20261020000000"},
            {"datname": "ofo_test_tpl_0046_x_bbbbbbbb", "comment": "ofo_tpl_ready 20261022110000"},
            {"datname": "ofo_test_tpl_0045_x_cccccccc", "comment": None},
            {"datname": "ofo_test", "comment": "ofo_tpl_ready 20200101000000"}]
    log = []
    dropped = asyncio.run(fresh.sweep_templates(TplConn(log, rows=rows), cur, NOW, lambda _m: None))
    assert dropped == [stale]
    assert drops(log) == [f'DROP DATABASE IF EXISTS "{stale}"']


def test_name_guard_mutants_are_caught_by_the_refusal_list():
    """Three mutants of the template-name guard (scratch copies, no server): each lets a name through that the real
    guard refuses, so the refusal list would fail if the real guard were changed that way."""
    import re
    real = fresh.TPL_RE.pattern
    refused = ["ofo_test", "ofo_dev", "ipodhan_prod", "postgres", "algochanakya", TPL + "x", "xofo_test_tpl_a_01234567"]
    mutants = {
        "match_not_fullmatch": lambda n: re.match(real, n) is not None,
        "prefix_widened": lambda n: re.fullmatch(real.replace("ofo_test_tpl_", "[a-z_]+"), n) is not None,
        "hash_part_loose": lambda n: re.fullmatch(real.replace("[0-9a-f]{8}", ".*"), n) is not None,
    }
    assert not any(fresh.is_template_name(n) for n in refused)
    for label, guard in mutants.items():
        assert any(guard(n) for n in refused), label
