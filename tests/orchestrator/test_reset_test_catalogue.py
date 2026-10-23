"""reset_test_catalogue.py with a fake connection: no real database is ever opened."""
import asyncio
import csv
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "orchestrator"))
import reset_test_catalogue as rtc

HOST = "postgresql://owner@127.0.0.1:5432"
GOOD = HOST + "/ofo_test"
ROWS = {"catalogue_term_changes": 2, "broker_instruments": 3, "catalogue_contracts": 4}
REFUSED_URLS = [HOST + "/" + name for name in
                ("ofo_dev", "ofo", "ipodhan", "postgres", "", "ofo_test_old", "OFO_TEST", "ofo_test?dbname=ofo_dev")
                ] + [HOST, ""]


class Rec(dict):
    pass


class FakeConn:
    def __init__(self, rows=None, fks=None, fk_counts=None, fail_on=None, backup_short=False):
        self.rows = dict(ROWS if rows is None else rows)
        self.fks = fks or {}
        self.fk_counts = fk_counts or {}
        self.fail_on = fail_on
        self.backup_short = backup_short
        self.statements = []
        self.rolled_back = False
        self.committed = False
        self.closed = False

    @asynccontextmanager
    async def transaction(self, **_kw):
        try:
            yield
        except BaseException:
            self.rolled_back = True
            raise
        self.committed = True

    async def fetchval(self, sql, *args):
        self.statements.append(sql)
        name = sql.split("public.")[1].split()[0].strip('"')
        return self.rows[name] if name in self.rows else self.fk_counts.get(name, 0)

    async def fetch(self, sql, *args):
        self.statements.append(sql)
        if "pg_constraint" in sql:
            parent = args[0].split('"')[1]
            return [{"child": c, "cols": cols} for c, cols in self.fks.get(parent, [])]
        table = sql.split('"')[1]
        n = self.rows[table] - (1 if self.backup_short else 0)
        return [Rec(id=i, v=None) for i in range(n)]

    async def execute(self, sql):
        self.statements.append(sql)
        if sql == self.fail_on:
            raise RuntimeError("OF006 delete refused by trigger")
        return f"DELETE {self.rows[sql.split(chr(34))[1]]}"

    async def close(self):
        self.closed = True


def go(url, yes, conn, tmp_path):
    calls = []

    async def connect(u):
        calls.append(u)
        return conn

    out = []
    rc = asyncio.run(rtc.run(url, yes, backup_root=str(tmp_path), connect=connect, out=out.append))
    return rc, calls, out


def deletes(conn):
    return [s for s in conn.statements if s.startswith("DELETE")]


@pytest.mark.parametrize("url", REFUSED_URLS)
def test_refused_names_exit_2_and_never_connect(url, tmp_path):
    conn = FakeConn()
    rc, calls, _ = go(url, True, conn, tmp_path)
    assert rc == rtc.EXIT_BAD_DB
    assert calls == []
    assert conn.statements == []


def test_dry_run_prints_counts_and_deletes_nothing(tmp_path):
    conn = FakeConn()
    rc, calls, out = go(GOOD, False, conn, tmp_path)
    assert rc == rtc.EXIT_OK
    assert len(calls) == 1
    assert deletes(conn) == []
    assert "catalogue_contracts: 4 row(s)" in out
    assert os.listdir(tmp_path) == []


def test_foreign_key_from_outside_allow_list_refuses(tmp_path):
    conn = FakeConn(fks={"catalogue_contracts": [("tracking_legs", ["contract_id"]),
                                                 ("broker_instruments", ["contract_id"])]},
                    fk_counts={"tracking_legs": 5})
    rc, _, out = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_REFUSED
    assert deletes(conn) == []
    assert any("tracking_legs has 5 row(s)" in line for line in out)


def test_foreign_key_with_zero_referencing_rows_passes(tmp_path):
    conn = FakeConn(fks={"catalogue_contracts": [("tracking_legs", ["contract_id"])]}, fk_counts={"tracking_legs": 0})
    rc, _, _ = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_OK


def test_backup_mismatch_refuses_before_any_delete(tmp_path):
    conn = FakeConn(backup_short=True)
    rc, _, out = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_REFUSED
    assert deletes(conn) == []
    assert conn.rolled_back
    assert any("backup of" in line for line in out)


def test_error_on_second_delete_rolls_back_the_transaction(tmp_path):
    second = 'DELETE FROM public."broker_instruments"'
    conn = FakeConn(fail_on=second)
    rc, _, out = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_REFUSED
    assert deletes(conn) == ['DELETE FROM public."catalogue_term_changes"', second]
    assert conn.rolled_back and not conn.committed
    assert any("rolled back" in line and "OF006" in line for line in out)


def test_full_run_issues_exactly_the_allow_listed_deletes_in_fk_order(tmp_path):
    conn = FakeConn()
    rc, _, _ = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_OK
    expected = ("catalogue_term_changes", "broker_instruments", "catalogue_contracts")
    assert deletes(conn) == [f'DELETE FROM public."{name}"' for name in expected]  # noqa: S608
    assert not any(word in s.upper() for s in conn.statements for word in ("CASCADE", "TRUNCATE", "TRIGGER"))
    assert conn.committed and conn.closed
    (stamp,) = os.listdir(tmp_path)
    folder = tmp_path / stamp
    assert sorted(os.listdir(folder)) == sorted(t + ".csv" for t in rtc.TABLES)
    with open(folder / "catalogue_contracts.csv", newline="", encoding="utf-8") as f:
        assert len(list(csv.reader(f))) == ROWS["catalogue_contracts"] + 1


def test_delete_count_differing_from_counted_rolls_back(tmp_path):
    class Drift(FakeConn):
        async def execute(self, sql):
            await super().execute(sql)
            return "DELETE 99"

    conn = Drift()
    rc, _, _ = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_REFUSED
    assert conn.rolled_back and not conn.committed


def test_connection_failure_is_reported_not_raised(tmp_path):
    async def boom(_url):
        raise OSError("tunnel down")

    out = []
    rc = asyncio.run(rtc.run(GOOD, True, backup_root=str(tmp_path), connect=boom, out=out.append))
    assert rc == rtc.EXIT_REFUSED
    assert any("CONNECTION FAILED" in line for line in out)


def _backup(folder, rows, drop=None):
    folder.mkdir()
    for t in rtc.TABLES:
        if t != drop:
            (folder / (t + ".csv")).write_text("id\n" + "1\n" * rows[t], encoding="utf-8")


def test_verify_backup_accepts_a_matching_folder(tmp_path):
    _backup(tmp_path / "b", ROWS)
    rtc.verify_backup(str(tmp_path / "b"), ROWS)


def test_verify_backup_refuses_a_short_file(tmp_path):
    _backup(tmp_path / "b", dict(ROWS, broker_instruments=1))
    with pytest.raises(rtc.Refused, match="broker_instruments"):
        rtc.verify_backup(str(tmp_path / "b"), ROWS)


def test_verify_backup_refuses_a_missing_file(tmp_path):
    _backup(tmp_path / "b", ROWS, drop="catalogue_contracts")
    with pytest.raises(rtc.Refused, match="one csv per table"):
        rtc.verify_backup(str(tmp_path / "b"), ROWS)


def test_fetched_row_count_is_checked_even_if_the_file_check_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(rtc, "verify_backup", lambda *_a: None)
    conn = FakeConn(backup_short=True)
    rc, _, _ = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_REFUSED
    assert deletes(conn) == []


def test_backup_is_verified_before_the_first_delete(tmp_path, monkeypatch):
    order = []
    conn = FakeConn()
    original = conn.execute

    async def spy(sql):
        order.append("delete")
        return await original(sql)

    conn.execute = spy
    monkeypatch.setattr(rtc, "verify_backup", lambda *_a: order.append("verify"))
    rc, _, _ = go(GOOD, True, conn, tmp_path)
    assert rc == rtc.EXIT_OK
    assert order == ["verify", "delete", "delete", "delete"]


def test_allow_list_is_exactly_three_tables():
    assert rtc.TABLES == ("catalogue_term_changes", "broker_instruments", "catalogue_contracts")
    assert rtc.ALLOWED_DATABASE == "ofo_test"
