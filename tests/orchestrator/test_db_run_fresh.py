"""db_run_fresh.py with a fake connection and a fake runner: no real database is ever created or dropped."""
import asyncio
import datetime
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

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
    code = fr.run(".", ["cmd"])
    return code, errs


@pytest.mark.parametrize("name", BAD_NAMES)
def test_drop_refuses_any_name_not_made_by_the_tool(name):
    log = []
    code = fresh.main(["--drop", name], connect=make_connect(log), settings_loader=lambda: SETTINGS)
    assert code == REFUSED
    assert drops(log) == [] and not any("pg_terminate" in s for s in sql(log))


def test_drop_accepts_the_tool_name_and_terminates_only_its_connections():
    log = []
    assert fresh.main(["--drop", GOOD], connect=make_connect(log), settings_loader=lambda: SETTINGS) == 0
    assert drops(log) == [f'DROP DATABASE IF EXISTS "{GOOD}"']
    assert any("datname = $1" in s for s in sql(log))


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


def test_create_refused_exit_3_and_still_drops_own_name_only():
    log, runner = [], Runner()
    code, errs = go(log, runner, fail_on="CREATE DATABASE")
    assert code == SETUP and any("step create failed" in e for e in errs)
    assert runner.calls == []
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
