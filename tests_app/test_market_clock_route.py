"""ADR-119 / finding freshness-judged-on-request-start-clock: the Execute route judges the market on a clock read
right before the gate (``_gate``) and again before the basket is returned (``_basket``), never on ``req.now``.
No database: the DB reads are replaced by stubs, the clock is a fake that advances past 15:30:00 between reads."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import json
from types import SimpleNamespace

import pytest
from ofo.timeutil import IST
from ofo_app import api_models
from ofo_app.routes import execute
from ofo_app.routes.strategies import StrategyRefused

START = datetime.datetime(2026, 10, 21, 15, 29, 59, tzinfo=IST)
LATE = datetime.datetime(2026, 10, 21, 15, 30, 1, tzinfo=IST)
NEXT_DAY = datetime.date(2026, 10, 22)


@dataclasses.dataclass(frozen=True)
class _Ctx:
    as_of: datetime.datetime
    market_open: bool | None


def _clock(*readings: datetime.datetime):
    """A clock that returns each reading once, then keeps the last (so an extra read cannot hide a bug)."""
    seen = list(readings)

    def read() -> datetime.datetime:
        return seen.pop(0) if len(seen) > 1 else seen[0]
    return read


def _req(clock):
    return SimpleNamespace(now=START, clock=clock, db=None, strategy_id=7, session=SimpleNamespace(margin=None))


def test_gate_judges_the_clock_read_right_before_it_not_request_start(monkeypatch) -> None:
    """Request starts 15:29:59 (req.now); the clock reads 15:30:01 at the gate: the gate's context carries 15:30:01 and
    market_open False, and the user is refused with the ADR-119 sentence. Without the re-read the spy sees 15:29:59."""
    async def fresh_registry(db, underlying):
        return None
    seen: list[_Ctx] = []

    monkeypatch.setattr(execute.elig, "fresh_registry", fresh_registry)
    monkeypatch.setattr(execute, "check_pre_execution", lambda s, ctx, *a, **k: seen.append(ctx) or SimpleNamespace(
        blocked=True, failures=[SimpleNamespace(message=execute.render("gate_market_closed", next_open=NEXT_DAY))],
        requires_confirmation=False))
    # the context the route built at request start says OPEN at 15:29:59
    ctx = _Ctx(as_of=START, market_open=True)
    priced = SimpleNamespace(strategy=None)
    with pytest.raises(StrategyRefused) as refused:
        asyncio.run(execute._gate(_req(_clock(LATE)), priced, ctx, None, "NIFTY"))
    assert seen[0].as_of == LATE and seen[0].market_open is False
    assert refused.value.args  # refused; the sentence itself is pinned by tests/execution/test_market_hours_gate.py


def test_gate_with_the_clock_still_inside_the_session_passes_the_market_context(monkeypatch) -> None:
    """Control: a clock still before 15:30:00 gives market_open True (the re-read does not close the gate by itself)."""
    async def fresh_registry(db, underlying):
        return None
    seen: list[_Ctx] = []
    monkeypatch.setattr(execute.elig, "fresh_registry", fresh_registry)
    monkeypatch.setattr(execute, "check_pre_execution", lambda s, ctx, *a, **k: seen.append(ctx) or SimpleNamespace(
        blocked=False, failures=[], requires_confirmation=False))
    asyncio.run(execute._gate(_req(_clock(START)), SimpleNamespace(strategy=None), _Ctx(START, True), None, "NIFTY"))
    assert seen[0].as_of == START and seen[0].market_open is True


def _stub_basket_path(monkeypatch) -> object:
    sentinel = object()

    async def limits(db, plan):
        return None
    monkeypatch.setattr(execute, "review_freeze_limits", limits)
    monkeypatch.setattr(execute, "freeze_check", lambda plan, limits, today: SimpleNamespace(blocks=[]))
    monkeypatch.setattr(execute, "checked_basket", lambda *a, **k: sentinel)
    monkeypatch.setattr(execute, "is_checked_basket", lambda basket: True)
    return sentinel


def test_basket_is_refused_when_margin_call_ran_past_the_close(monkeypatch) -> None:
    """The gate passed at 15:29:59; Zerodha's margin call returned at 15:30:01: no basket leaves."""
    _stub_basket_path(monkeypatch)
    req = _req(_clock(LATE))
    with pytest.raises(StrategyRefused):
        asyncio.run(execute._basket(req, SimpleNamespace(plan=None), None, 1))


def test_basket_is_returned_when_the_clock_is_still_open(monkeypatch) -> None:
    sentinel = _stub_basket_path(monkeypatch)
    assert asyncio.run(execute._basket(_req(_clock(START)), SimpleNamespace(plan=None), None, 1)) is sentinel


# ---- the screen's read: the same verdict, before the click ----------------------------------------------------

def _verdict(when: datetime.datetime) -> dict:
    return json.loads(api_models.emit(execute.market_verdict(when)))


def test_market_status_route_is_the_gates_verdict_in_each_state() -> None:
    """Open Wed 10:00; closed on Dussehra with the ADR-119 / ADR-121 sentence and the next trading day; unconfirmed in a
    year with no holiday data (no date guessed). The route is mounted and uses the server clock dependency."""
    opened = _verdict(datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST))
    assert opened["status"] == "open" and opened["next_open"] is None and opened["message"] is None
    closed = _verdict(datetime.datetime(2026, 10, 20, 10, 0, tzinfo=IST))
    assert closed["status"] == "closed" and closed["next_open"] == "2026-10-21"
    assert closed["message"]["what_happened"] == (
        "Market closed. You can review your plan; execution opens at 09:15 on Wed 21 Oct.")
    unknown = _verdict(datetime.datetime(2027, 1, 5, 10, 0, tzinfo=IST))
    assert unknown["status"] == "unconfirmed" and unknown["next_open"] is None
    assert unknown["message"]["what_happened"].startswith("We could not confirm that the market is open")
    assert any(r.path == "/execute/market-status" and "GET" in r.methods for r in execute.router.routes)


def test_market_status_route_serves_the_server_clock() -> None:
    out = asyncio.run(execute.execute_market_status(lambda: LATE))
    assert out.status == "closed" and out.as_of == LATE
