"""Lane FD round 2 (B1, I-47): ``place_paper_orders`` holds no pooled connection while the first fill's entry facts wait
on the market (the entry ATM IV is a REST read, ``entry_facts`` -> ``atm_iv_now``).

RCA: the route released its connection before the exit price read, but ``paper_store.tracked_ids`` (the "is this the
first fill" read) started a new read transaction after it, and ``entry_facts`` awaited the broker inside it. Class: a
read between two market waits re-checks out the connection; every wait must have a release right before it.

No database: the session is a recorder (``open`` = a transaction is open, so a pooled connection is held). Every
collaborator of the route is stubbed; the proof is the state of ``open`` at the moment the market wait starts.
"""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from ofo_app.routes import paper


class _Db:
    def __init__(self) -> None:
        self.open = False

    async def commit(self) -> None:
        self.open = False

    async def rollback(self) -> None:
        self.open = False


async def _kind_paper(*_a):
    return "paper"


async def _not_records(*_a):
    return False


class _Stop(Exception):  # ends the route after the waits, so nothing else is needed
    pass


def _world(monkeypatch, *, first: bool):
    db = _Db()
    seen: dict[str, bool] = {}
    stored = SimpleNamespace(saved=SimpleNamespace(definition=SimpleNamespace(underlying="NIFTY")))
    contract = SimpleNamespace(contract_id=1, state="live", stored=SimpleNamespace())

    async def load(d, *_a):
        d.open = True
        return stored

    async def resolve(d, _ids):
        d.open = True
        return [contract]

    async def exit_prices(*_a):
        seen["exit_prices"] = db.open
        return {}

    async def tracked_ids(d, _ids):
        d.open = True  # a read starts a transaction: the connection is checked out
        return [] if first else [7]

    async def entry_facts(*_a, **_k):
        seen["entry_facts"] = db.open

    async def place_checked(*_a, **_k):
        raise _Stop

    async def no_stops(*_a):
        return []

    async def lock(*_a):
        return None

    monkeypatch.setattr(paper.store, "lock_strategy", lock)  # I-158: the lock is taken before the armed read
    monkeypatch.setattr(paper, "_armed_leg_stops", no_stops)  # FD2: the stops read is not what this file measures
    monkeypatch.setattr(paper, "_load_strategy", load)
    monkeypatch.setattr(paper.tracked_contracts, "resolve", resolve)
    monkeypatch.setattr(paper, "_server_exit_prices", exit_prices)
    monkeypatch.setattr(paper.paper_store, "tracked_ids", tracked_ids)
    monkeypatch.setattr(paper, "entry_facts", entry_facts)
    monkeypatch.setattr(paper, "_refuse_real_position", _kind_paper)  # Lane R1: the one kind read is not measured here
    monkeypatch.setattr(paper, "_records_door", _not_records)
    monkeypatch.setattr(paper, "_refuse_duplicate_legs", lambda *_a: None)
    monkeypatch.setattr(paper, "_check_held", lambda *_a: None)
    monkeypatch.setattr(paper.may_act, "refuse_unless_allowed", lambda *_a: None)
    monkeypatch.setattr(paper.paper_limit, "place_checked", place_checked)
    order = SimpleNamespace(kind="open", price=Decimal("1.00"), contract_id=1, side="SELL", quantity=1)
    body = SimpleNamespace(orders=[order], approach_id=None, held=None, prices_not_live_confirmed=False,
                           suggestion_ids=[], basket_legs=None, client_request_id=None)
    return db, seen, body


async def _call(db, body):
    now = datetime.datetime(2026, 11, 27, 10, 0, tzinfo=datetime.UTC)
    with pytest.raises(_Stop):
        await paper.place_paper_orders(1, body, db, "u", None, None, lambda: now, None, None, {}, None)


async def test_the_first_fill_gives_the_connection_back_before_the_entry_facts_wait(monkeypatch):
    db, seen, body = _world(monkeypatch, first=True)
    await _call(db, body)
    assert seen["exit_prices"] is False  # as before (Lane R)
    assert seen["entry_facts"] is False  # the entry IV read waits on the broker: no connection held


async def test_a_later_fill_reads_no_entry_facts(monkeypatch):
    db, seen, body = _world(monkeypatch, first=False)
    await _call(db, body)
    assert seen["exit_prices"] is False
    assert "entry_facts" not in seen
