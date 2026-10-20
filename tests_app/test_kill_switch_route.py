"""ADR-127 without a database: the Execute route reads the kill switch FRESH at the gate and again before the basket
leaves, the screen's verdict says ``paused``, and the owner check fails closed. (The end-to-end proof on PostgreSQL is
``test_execute_kill_switch.py``.) Each test names the guard whose removal makes it fail."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import json
from http import HTTPStatus
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from ofo.timeutil import IST
from ofo_app import api_models, errors, kill_switch
from ofo_app.config import OWNER_KEY_MIN
from ofo_app.db import get_db
from ofo_app.routes import execute
from ofo_app.routes import kill_switch as owner_route
from ofo_app.routes.strategies import StrategyRefused
from sqlalchemy.exc import SQLAlchemyError

OPEN_NOW = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)  # Wednesday, market open
ADR_127 = ("Execution is paused by the platform right now. You can review and save your plan; "
           "no orders can be sent.")


@dataclasses.dataclass(frozen=True)
class _Ctx:
    as_of: datetime.datetime
    market_open: bool | None
    platform_paused: bool | None


def _reads(*values):
    """is_paused stub: each call returns the next value (then the last), and counts the calls."""
    seen = list(values)
    calls = []

    async def read(db):
        calls.append(db)
        return seen.pop(0) if len(seen) > 1 else seen[0]
    read.calls = calls
    return read


def _gate_spy(monkeypatch):
    async def fresh_registry(db, underlying):
        return None
    seen = []
    monkeypatch.setattr(execute.elig, "fresh_registry", fresh_registry)
    monkeypatch.setattr(execute, "check_pre_execution", lambda s, ctx, *a, **k: seen.append(ctx) or SimpleNamespace(
        blocked=False, failures=[], requires_confirmation=False))
    return seen


def _req():
    return SimpleNamespace(now=OPEN_NOW, clock=lambda: OPEN_NOW, db="db", strategy_id=7,
                           session=SimpleNamespace(margin=None))


# ---- the gate reads the switch fresh (guard: the dataclasses.replace in execute._gate) ------------------------------

def test_gate_uses_the_switch_read_right_before_it_not_the_request_start_value(monkeypatch) -> None:
    """The context built at request start says OFF; the owner flips it on during the slow reads; the gate's context
    carries ON. Remove the re-read in ``_gate`` and the spy sees False."""
    seen = _gate_spy(monkeypatch)
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(True))
    asyncio.run(execute._gate(_req(), SimpleNamespace(strategy=None), _Ctx(OPEN_NOW, True, False), None, "NIFTY"))
    assert seen[0].platform_paused is True


def test_gate_reads_every_time_never_a_cached_value(monkeypatch) -> None:
    seen = _gate_spy(monkeypatch)
    read = _reads(False, True, False)
    monkeypatch.setattr(execute.kill_switch, "is_paused", read)
    for _ in range(3):
        asyncio.run(execute._gate(_req(), SimpleNamespace(strategy=None), _Ctx(OPEN_NOW, True, False), None, "NIFTY"))
    expected = [False, True, False]
    assert [c.platform_paused for c in seen] == expected and len(read.calls) == len(expected)


def _stub_basket_path(monkeypatch) -> object:
    sentinel = object()

    async def limits(db, plan):
        return None
    monkeypatch.setattr(execute, "review_freeze_limits", limits)
    monkeypatch.setattr(execute, "freeze_check", lambda plan, limits, today: SimpleNamespace(blocks=[]))
    monkeypatch.setattr(execute, "checked_basket", lambda *a, **k: sentinel)
    monkeypatch.setattr(execute, "is_checked_basket", lambda basket: True)
    return sentinel


def test_basket_is_refused_when_the_switch_went_on_during_zerodhas_margin_call(monkeypatch) -> None:
    """Guard: the re-read in ``_basket``. The gate passed (off); the owner flipped it on while the margin call ran."""
    _stub_basket_path(monkeypatch)
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(True))
    with pytest.raises(StrategyRefused) as refused:
        asyncio.run(execute._basket(_req(), SimpleNamespace(plan=None), None, 1))
    assert refused.value.message.what_happened == ADR_127


def test_basket_is_returned_when_the_switch_is_off(monkeypatch) -> None:
    sentinel = _stub_basket_path(monkeypatch)
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(False))
    assert asyncio.run(execute._basket(_req(), SimpleNamespace(plan=None), None, 1)) is sentinel


def test_basket_is_refused_when_the_switch_cannot_be_read(monkeypatch) -> None:
    """Guard: unknown (None) counts as paused."""
    _stub_basket_path(monkeypatch)
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(None))
    with pytest.raises(StrategyRefused):
        asyncio.run(execute._basket(_req(), SimpleNamespace(plan=None), None, 1))


# ---- the screen's read ---------------------------------------------------------------------------------------------

def _verdict(paused) -> dict:
    return json.loads(api_models.emit(execute.market_verdict(OPEN_NOW, paused)))


def test_screen_verdict_is_paused_with_the_adr127_sentence_while_the_market_is_open() -> None:
    on = _verdict(True)
    assert on["status"] == "paused" and on["next_open"] is None and on["message"]["what_happened"] == ADR_127
    assert _verdict(None)["status"] == "paused"  # unknown fails closed
    assert _verdict(False)["status"] == "open"


def test_market_status_route_reads_the_switch_per_request(monkeypatch) -> None:
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(True, False))
    assert asyncio.run(execute.execute_market_status(lambda: OPEN_NOW, "db", "u1")).status == "paused"
    assert asyncio.run(execute.execute_market_status(lambda: OPEN_NOW, "db", "u1")).status == "open"


# ---- the stored switch: the latest audit event is the state ----------------------------------------------------------

class _Conn:
    def __init__(self, row=None, error=None):
        self._row, self._error = row, error

    async def execute(self, *_a, **_k):
        if self._error:
            raise self._error
        return SimpleNamespace(first=lambda: self._row)


@pytest.mark.parametrize("row, expected", [
    (None, False),
    (SimpleNamespace(action="kill_switch_on"), True),
    (SimpleNamespace(action="kill_switch_off"), False),
    (SimpleNamespace(action="something_else"), None),
])
def test_is_paused_states(row, expected) -> None:
    assert asyncio.run(kill_switch.is_paused(_Conn(row))) is expected


def test_is_paused_unreadable_is_unknown_not_off() -> None:
    assert asyncio.run(kill_switch.is_paused(_Conn(error=SQLAlchemyError("down")))) is None


# ---- the owner check fails closed ------------------------------------------------------------------------------------

def _refused(header) -> bool:
    try:
        owner_route.require_owner(header)
    except StrategyRefused as exc:
        return exc.failure is not None and exc.failure.status == HTTPStatus.NOT_FOUND
    return False


def test_owner_check(monkeypatch) -> None:
    key = "k" * OWNER_KEY_MIN
    monkeypatch.setenv("OFO_OWNER_KEY", key)
    assert owner_route.require_owner(key) is None  # the right key passes
    assert _refused(None) and _refused("x" * OWNER_KEY_MIN) and _refused(key + "x") and _refused("")
    monkeypatch.setenv("OFO_OWNER_KEY", "")
    assert _refused(key)  # no key on the server: nobody is the owner
    monkeypatch.delenv("OFO_OWNER_KEY")
    assert _refused(key)
    monkeypatch.setenv("OFO_OWNER_KEY", "k" * (OWNER_KEY_MIN - 1))
    assert _refused("k" * (OWNER_KEY_MIN - 1))  # a key below the minimum length is no key


def test_the_flip_route_is_mounted_put_only_behind_the_owner_check() -> None:
    (route,) = [r for r in owner_route.router.routes if r.path == "/admin/kill-switch"]
    assert route.methods == {"PUT"}
    assert any(d.call is owner_route.require_owner for d in route.dependant.dependencies)


# ---- round 1: the route reveals nothing before the owner check, the context reads the switch, ADR-128 ----------------

def _mini_app(monkeypatch):
    """The real owner router and the real error handlers, a stub DB; no PostgreSQL."""
    key = "k" * OWNER_KEY_MIN
    monkeypatch.setenv("OFO_OWNER_KEY", key)
    flips = []

    class Db:
        async def commit(self): ...
        async def rollback(self): ...

    async def fake_set(conn, paused, *, reason, actor="owner"):
        flips.append((paused, reason))
        return 1
    monkeypatch.setattr(owner_route.kill_switch, "set_paused", fake_set)
    app = FastAPI()
    errors.install(app)
    app.include_router(owner_route.router)
    app.dependency_overrides[get_db] = Db
    return TestClient(app, raise_server_exceptions=False), key, flips


def test_malformed_json_without_the_key_is_a_404_like_an_unknown_path(monkeypatch) -> None:
    """Guard: the owner check runs BEFORE the body is parsed (a declared ``body: KillSwitchIn`` gives 422)."""
    client, _key, flips = _mini_app(monkeypatch)
    json_head = {"content-type": "application/json"}
    unknown = client.put("/admin/no-such-route", content=b"{not json", headers=json_head)
    for headers in ({}, {"X-Owner-Key": "x" * OWNER_KEY_MIN}):
        stranger = client.put("/admin/kill-switch", content=b"{not json", headers={**json_head, **headers})
        assert stranger.status_code == HTTPStatus.NOT_FOUND and stranger.json() == unknown.json()
    wrong_shape = client.put("/admin/kill-switch", json={"paused": "yes"})
    assert wrong_shape.status_code == HTTPStatus.NOT_FOUND and wrong_shape.json() == unknown.json()
    assert flips == []


def test_owner_with_a_malformed_or_wrong_body_gets_422_and_nothing_is_flipped(monkeypatch) -> None:
    client, key, flips = _mini_app(monkeypatch)
    head = {"X-Owner-Key": key, "content-type": "application/json"}
    unprocessable = HTTPStatus.UNPROCESSABLE_ENTITY
    assert client.put("/admin/kill-switch", content=b"{not json", headers=head).status_code == unprocessable
    assert client.put("/admin/kill-switch", content=json.dumps({"paused": "yes", "reason": "r"}),
                      headers=head).status_code == unprocessable
    assert client.put("/admin/kill-switch", content=json.dumps({"paused": True}), headers=head
                      ).status_code == unprocessable
    assert flips == []
    ok = client.put("/admin/kill-switch", content=json.dumps({"paused": True, "reason": "r"}), headers=head)
    assert ok.status_code == HTTPStatus.OK and ok.json() == {"paused": True} and flips == [(True, "r")]


def test_context_build_reads_the_switch_not_a_constant(monkeypatch) -> None:
    """Guard: the ``platform_paused=`` read in ``execute._context``; a constant False there fails this (mutation M4)."""
    async def margin(req, priced, catalogue):
        return None, None

    async def none(*a, **k):
        return None

    async def now(db):
        return OPEN_NOW
    monkeypatch.setattr(execute, "_zerodha_margin", margin)
    monkeypatch.setattr(execute, "_positions", none)
    monkeypatch.setattr(execute, "_pro_entitled", none)
    async def health(*a, **k):
        return {}
    monkeypatch.setattr(execute, "_data_health", health)
    monkeypatch.setattr(execute, "_reconciliation", lambda *a, **k: frozenset())
    monkeypatch.setattr(execute.elig, "database_now", now)
    req = SimpleNamespace(now=OPEN_NOW, clock=lambda: OPEN_NOW, db="db", strategy_id=7, action=execute.ENTRY)
    definition = SimpleNamespace(underlying="NIFTY", rules_ref=None)
    stored = SimpleNamespace(revision=1, saved=SimpleNamespace(definition=definition))
    held = execute._Held({}, None, None, ())
    for value in (True, None, False):
        monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(value))
        context, _figures = asyncio.run(execute._context(req, stored, SimpleNamespace(price_bands=None), held, None))
        assert context.platform_paused is value


ADR_128 = "You can still close positions directly on Kite."


def test_adr128_hint_only_while_paused_and_only_with_an_open_position() -> None:
    held = json.loads(api_models.emit(execute.market_verdict(OPEN_NOW, True, open_position=True)))
    assert held["message"]["what_happened"] == ADR_127 and held["paused_hint"]["what_happened"] == ADR_128
    for paused, position in ((True, False), (False, True), (False, False)):
        verdict = execute.market_verdict(OPEN_NOW, paused, open_position=position)
        assert json.loads(api_models.emit(verdict))["paused_hint"] is None


def _units(monkeypatch, units=None, error=None):
    async def plans_for(db, user_ref, strategy_id):
        if error:
            raise error
        return ("history", user_ref, strategy_id)
    monkeypatch.setattr(execute.plans, "plans_for", plans_for)
    monkeypatch.setattr(execute.ep, "held_units", lambda history: units or {})


def _status(monkeypatch, paused, **kw):
    monkeypatch.setattr(execute.kill_switch, "is_paused", _reads(paused))
    return asyncio.run(execute.execute_market_status(lambda: OPEN_NOW, "db", "u1", **kw))


def test_market_status_route_adds_the_hint_for_a_held_strategy_while_paused(monkeypatch) -> None:
    _units(monkeypatch, {"c1": 65})
    on = _status(monkeypatch, True, strategy_id=9)
    assert on.status == "paused" and on.paused_hint.what_happened == ADR_128
    assert _status(monkeypatch, True).paused_hint is None  # no strategy asked about: nothing to say
    assert _status(monkeypatch, False, strategy_id=9).paused_hint is None
    _units(monkeypatch, {"c1": 0})
    assert _status(monkeypatch, True, strategy_id=9).paused_hint is None  # flat: only the ADR-127 sentence
    _units(monkeypatch, error=SQLAlchemyError("down"))
    unreadable = _status(monkeypatch, True, strategy_id=9)
    assert unreadable.status == "paused" and unreadable.paused_hint is None  # never guessed
