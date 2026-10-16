"""#263 item 3: a same-date freeze load that loses the insert race must compare, never silently keep the wrong value.

Class: a check-then-insert with ``ON CONFLICT DO NOTHING`` and no compare on conflict. The pre-check sees no row, a
concurrent load inserts a different limit, our insert conflicts (rowcount 0) and the old code dropped ours silently.
No database needed: a scripted connection plays exactly that interleaving against the real ``load_freeze_file``.
"""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from ofo.instruments.models import InstrumentId, NSE_FO
from ofo_app import freeze_store

FILE_DATE = datetime.date(2026, 10, 15)
TOKEN = 47185


class _Result:
    def __init__(self, rows=(), scalar=None, rowcount=0) -> None:
        self._rows, self._scalar, self.rowcount = list(rows), scalar, rowcount

    def all(self):  # noqa: ANN201
        return self._rows

    def scalar_one(self):  # noqa: ANN201
        return self._scalar

    def scalar_one_or_none(self):  # noqa: ANN201
        return self._scalar


class _Nested:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False


class _RacedConn:
    """Pre-check: nothing stored. Insert: conflicts (a concurrent load won). Re-read: that load's value."""

    def __init__(self, raced_value: int) -> None:
        self.raced_value = raced_value

    def begin_nested(self) -> _Nested:
        return _Nested()

    async def execute(self, statement, params=None):  # noqa: ANN001, ANN201
        if statement is freeze_store._TODAY_IST:
            return _Result(scalar=FILE_DATE)
        if statement is freeze_store._SAME_DAY:
            return _Result()
        if statement is freeze_store._INSERT:
            return _Result(rowcount=0)
        if statement is freeze_store._STORED_ONE:
            return _Result(scalar=self.raced_value)
        raise AssertionError(f"unexpected statement {statement}")


@pytest.fixture
def one_row(monkeypatch):  # noqa: ANN001, ANN201
    parsed = SimpleNamespace(file_date=FILE_DATE)
    join = SimpleNamespace(matched=[SimpleNamespace(instrument_id=InstrumentId(NSE_FO, TOKEN), freeze_limit=3511)],
                           not_in_catalogue=0, disagreements=())
    monkeypatch.setattr(freeze_store, "parse_freeze_file", lambda path, nse_name=None: parsed)
    monkeypatch.setattr(freeze_store, "match_to_catalogue", lambda p, c: join)

    async def _catalogue(conn):  # noqa: ANN001, ANN202
        return None

    monkeypatch.setattr(freeze_store, "load_catalogue", _catalogue)


async def test_a_conflict_with_a_different_stored_limit_raises(one_row) -> None:  # noqa: ANN001
    with pytest.raises(ValueError, match="47185.*3511.*3510"):
        await freeze_store.load_freeze_file(_RacedConn(3510), "NSE_FO_contract_15102026.csv")


async def test_a_conflict_with_the_same_stored_limit_is_already_stored(one_row) -> None:  # noqa: ANN001
    result = await freeze_store.load_freeze_file(_RacedConn(3511), "NSE_FO_contract_15102026.csv")
    assert (result.inserted, result.already_stored) == (0, 1)
