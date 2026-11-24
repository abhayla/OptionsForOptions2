"""D-04 round 3 (ADR-318 (4)): ONE spot-free door classifies the entry shape for every caller. A short strangle (call
24000, put 23600; middle of the strikes 23800) is a "strangle" read with no spot, but with a live spot of 24100 the
matcher reads it as no template: a caller that passed the live spot read another playbook (plan maximum, rules) than
the server's limit. No database: the stores and the reads are faked; the classifier is the real code."""
from __future__ import annotations

import ast
import asyncio
import pathlib
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from ofo_app import adjustment_check as check
from ofo_app import adjustment_readers as readers
from ofo_app import paper_book, paper_limit, playbook_store, tracked_contracts
from ofo_app.routes import adjustment_plan, playbooks
from test_d04_entry_shape import GAP, T0, _contract, _order

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIVE_SPOT = D(24100)  # the middle of the strikes is 23800: the live spot reads this shape as no template
SHAPE = [_order(1, "SELL", "open", T0), _order(3, "SELL", "open", T0)]  # a short strangle, no adjustment yet
DOOR_CALLERS = ("backend/ofo_app/paper_limit.py", "backend/ofo_app/adjustment_readers.py",
                "backend/ofo_app/background.py", "backend/ofo_app/routes/adjustment_check.py",
                "backend/ofo_app/routes/adjustment_plan.py", "backend/ofo_app/routes/playbooks.py",
                "backend/ofo_app/routes/adjustment_history.py", "backend/ofo_app/routes/adjustment.py")


@pytest.fixture
def tracked(monkeypatch):
    async def load_owned(*_a):
        return SHAPE

    async def resolve(_db, ids):
        return [_contract(i) for i in ids]
    async def plan_for(*_a):
        return None
    monkeypatch.setattr(playbook_store, "plan_for", plan_for)
    monkeypatch.setattr(paper_book, "load_owned", load_owned)
    monkeypatch.setattr(tracked_contracts, "resolve", resolve)
    monkeypatch.setattr(check, "strike_gap_of", lambda *_a: GAP)
    return asyncio.run(readers._tracked_on(None, 164, None))


@pytest.fixture
def asked(monkeypatch):
    """The playbook type each path asked the store for (``check.resolve``'s last argument)."""
    seen: list[str | None] = []

    async def resolve(_db, _user, _sid, stype):
        seen.append(stype)
        return check.Resolved("system", {"guards": {"max_adjustments": 2}}, 1, "system", False,
                              saved_before_adr247=False)
    monkeypatch.setattr(check, "resolve", resolve)
    return seen


def test_the_shape_reads_differently_with_the_live_spot_than_without(tracked):
    """The premise: the classifier itself is spot-dependent for this shape, so a caller's spot argument matters."""
    assert check.strategy_type(tracked.position, None, []) == "strangle"
    assert check.strategy_type(tracked.position, LIVE_SPOT, []) is None


def test_the_server_limit_reads_the_strangle_playbook(tracked, asked):
    async def reader(_sid, _rates):
        return tracked
    asyncio.run(paper_limit._plan_body(None, "u", 164, reader, None, []))
    assert asked == ["strangle"]


def test_the_offer_path_reads_the_same_type_whatever_spot_it_is_given(tracked, asked):
    asyncio.run(readers.read_guards(164, tracked, LIVE_SPOT, [], db=object()))
    asyncio.run(readers.read_guards(164, tracked, None, [], db=object()))
    assert asked == ["strangle", "strangle"]


def test_the_plan_route_reads_the_server_limits_type_with_a_live_spot(tracked, monkeypatch):
    async def plan_for(*_a):
        return None

    async def market_reader(*_a):
        return object()

    async def rest_reader(_underlying):
        return None
    monkeypatch.setattr(adjustment_plan.store, "plan_for", plan_for)
    monkeypatch.setattr(adjustment_plan, "judge_spot", lambda *_a: SimpleNamespace(available=True, value=LIVE_SPOT))
    ctx = SimpleNamespace(provider=SimpleNamespace(instrument_master=list))
    stype, plan = asyncio.run(adjustment_plan._type_of(None, "u", 164, tracked, market_reader, rest_reader, ctx))
    assert (stype, plan) == ("strangle", None)


def test_the_playbooks_test_route_reads_the_server_limits_type_with_a_live_spot(tracked, monkeypatch):
    async def read_one(_row, _seams, _listed, read):
        read.tracked, read.spot = tracked, SimpleNamespace(available=True, value=LIVE_SPOT)
    monkeypatch.setattr(playbooks, "_read_one", read_one)
    data = SimpleNamespace(type="strangle", body={"rules": []})
    found = asyncio.run(playbooks._read_bounded(SimpleNamespace(id=164), None, [], asyncio.Semaphore(1), data))
    assert found is not None and found[0].id == 164  # of the type the server's limit reads, so it is tested


def _entry_type_calls(path: str) -> list[ast.Call]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and getattr(n.func, "attr", getattr(n.func, "id", None)) == "entry_type"]


def test_no_caller_hands_the_door_a_spot():
    """The check route and the worker (and every other caller) call the door with the tracked strategy and the listing
    only: a spot cannot reach the classification, so a caller cannot read another playbook than the server limit."""
    calls = {p: _entry_type_calls(p) for p in DOOR_CALLERS}
    assert sum(len(v) for v in calls.values()) >= 8  # noqa: PLR2004 - the eight call sites of D-04 are still found
    for path, found in calls.items():
        for call in found:
            assert len(call.args) + len(call.keywords) == 2, f"{path}:{call.lineno} passes more than (tracked, listed)"  # noqa: PLR2004


def test_the_door_has_no_spot_parameter():
    import inspect
    assert list(inspect.signature(check.entry_type).parameters) == ["tracked", "listed"]
