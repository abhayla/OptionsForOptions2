# ruff: noqa: PLR2004, S106
"""REQ-015 AC-13 (RD-013): Settings shows the masked Zerodha client id and, with ``funds_read`` on, Zerodha's own
available margin exactly as read with its read time; every other state is a reason, never 0 (ADR-016).

DB-free: the route function is called with a fake session over a counting fake Kite transport (no network, no Kite).
Expected figures are the reply's own text (``"12345.67"`` in, ``"12345.67"`` out), never computed.
"""
from __future__ import annotations

import datetime
import json

import pytest
from ofo.broker import rate_limit
from ofo.broker.rate_limit import RateLimiter
from ofo_app import kite_period_reads
from ofo_app.kite_margin import KiteMargin
from ofo_app.kite_reads import KiteReads
from ofo_app.routes import broker_account as route

T0 = datetime.datetime(2026, 10, 23, 9, 30, 0, tzinfo=datetime.UTC)
PROFILE = {"user_id": "AB1234", "broker": "ZERODHA", "exchanges": ["NFO"], "products": ["NRML"],
           "order_types": ["LIMIT"]}


class Clock:
    t = 0.0

    def now(self) -> float:
        return self.t

    def sleep_until(self, at: float) -> None:
        return None

    async def asleep_until(self, at: float) -> None:
        return None


class Wire:
    def __init__(self, margins: object = None, status: int = 200, profile_status: int = 200) -> None:
        self.margins = {"equity": {"net": "MARGIN"}} if margins is None else margins
        self.status, self.profile_status, self.calls = status, profile_status, []

    def __call__(self, method, url, headers, body):
        path = url.split("kite.trade", 1)[-1]
        self.calls.append(path)
        status = self.profile_status if path == "/user/profile" else self.status
        if status != 200:
            kind = "TokenException" if status == 403 else "NetworkException"
            return status, json.dumps({"status": "error", "message": "x", "error_type": kind})
        data = PROFILE if path == "/user/profile" else self.margins
        # the figure goes in as a JSON number written by hand, so the parse is Zerodha's text exactly
        return 200, json.dumps({"status": "success", "data": data}).replace('"MARGIN"', "12345.67")


class _Session:
    def __init__(self, wire: Wire) -> None:
        self.api_key = "KEY"
        self.reads = KiteReads(api_key="KEY", access_token="tok-account", transport=wire)
        self.margin = KiteMargin(api_key="KEY", access_token="tok-account", transport=wire)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(kite_period_reads, "utc_now", lambda: T0 + datetime.timedelta(seconds=c.t))
    with rate_limit.use(RateLimiter(pacer=c)):
        yield c


def _flags(monkeypatch, on: bool | None) -> None:
    from ofo.broker import kite_flags  # noqa: PLC0415
    from ofo.broker.flags import FlagSet, FlagValue  # noqa: PLC0415

    def load():
        if on is None:
            raise OSError("flag file unreadable")
        return FlagSet({"funds_read": FlagValue(on, "tests", datetime.date(2026, 10, 23))})
    monkeypatch.setattr(kite_flags, "load_zerodha_flags", load)


async def _get(session) -> dict:
    return (await route.broker_account(session)).model_dump(mode="json")


async def test_ac13_masked_id_and_the_margin_exactly_as_read_with_its_read_time(monkeypatch):
    """AC-13: id AB1234 -> AB + 2 hidden + 34 (the full id is not in the answer); margin "12345.67" as read, at T0."""
    _flags(monkeypatch, True)
    body = await _get(_Session(Wire()))
    assert body == {"user_id": {"start": "AB", "hidden": 2, "end": "34"},
                    "margin": {"state": "available", "available": "12345.67", "read_at": "2026-10-23T09:30:00Z"}}
    assert "AB1234" not in json.dumps(body)


async def test_ac13_inside_30_s_the_same_answer_comes_back_with_the_first_read_time(monkeypatch, clock):
    """AC-13 + REQ-118 AC-7: a second ask at +10 s makes no Kite call and keeps the first read's time."""
    _flags(monkeypatch, True)
    wire = Wire()
    session = _Session(wire)
    await _get(session)
    clock.t = 10.0
    body = await _get(session)
    assert body["margin"]["read_at"] == "2026-10-23T09:30:00Z" and len(wire.calls) == 2  # profile + margins once


@pytest.mark.parametrize(("wire", "state"), [
    (Wire(margins={"equity": {}}), "empty"), (Wire(margins={}), "empty"),
    (Wire(margins={"equity": {"net": "x"}}), "empty"),
    (Wire(status=503), "read_failed"), (Wire(status=429), "busy"), (Wire(status=403), "session_expired"),
    (Wire(status=400), "read_failed")])
async def test_ac13_every_failed_margin_read_is_a_reason_never_zero(monkeypatch, wire, state):
    """AC-13 / standing item (d): absent field, empty, failed, rate-limited, token expired -> a reason, no figure."""
    _flags(monkeypatch, True)
    body = await _get(_Session(wire))
    assert body["margin"] == {"state": state, "available": None, "read_at": None}


@pytest.mark.parametrize("on", [False, None])
async def test_ac13_funds_read_off_or_unloadable_reads_no_margin(monkeypatch, on):
    """AC-13 + REQ-117 fail closed: flag off or its file broken -> not_offered, and /user/margins is never called."""
    _flags(monkeypatch, on)
    wire = Wire()
    body = await _get(_Session(wire))
    assert body["margin"] == {"state": "not_offered", "available": None, "read_at": None}
    assert "/user/margins" not in wire.calls


async def test_ac13_not_connected_reads_nothing_and_says_so(monkeypatch):
    _flags(monkeypatch, True)
    assert await _get(None) == {"user_id": None,
                                "margin": {"state": "not_connected", "available": None, "read_at": None}}


async def test_ac13_a_failed_profile_read_gives_no_id_and_leaves_the_margin_alone(monkeypatch):
    _flags(monkeypatch, True)
    body = await _get(_Session(Wire(profile_status=503)))
    assert body["user_id"] is None and body["margin"]["available"] == "12345.67"


@pytest.mark.parametrize(("uid", "parts"), [("AB1234", ("AB", 2, "34")), ("ZX98765", ("ZX", 3, "65")),
                                            ("ABCD", (None, 4, None)), ("A", (None, 1, None))])
def test_ac13_the_mask_shows_first_two_and_last_two_only(uid, parts):
    assert kite_period_reads.mask_user_id(uid) == parts


@pytest.mark.parametrize("uid", ["", "   ", None, 5])
def test_ac13_no_id_is_refused_not_masked(uid):
    with pytest.raises(ValueError):
        kite_period_reads.mask_user_id(uid)
