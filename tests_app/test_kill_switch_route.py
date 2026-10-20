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
from ofo.timeutil import IST
from ofo_app import api_models, kill_switch
from ofo_app.config import OWNER_KEY_MIN
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
    assert asyncio.run(execute.execute_market_status(lambda: OPEN_NOW, "db")).status == "paused"
    assert asyncio.run(execute.execute_market_status(lambda: OPEN_NOW, "db")).status == "open"


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
