"""AC-3 (W-077, issue #249; ADR-086 "every leg is named by its contract"): with no live provider the outcome route names
each leg from the STORED catalogue (the same contract fields the computed path returns); a contract the catalogue does
not know keeps None (the page's fixed wording), never an instrument id; a catalogue that cannot be read still answers.
The stored catalogue is the recorded real NIFTY/SENSEX instrument rows of tests/marketdata (the expected fields are read
from those rows, not from the code under test). No database is needed: the lookup dependency is replaced."""
from __future__ import annotations

import pathlib
import sys

from httpx import ASGITransport, AsyncClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from marketdata._kite_fixture import listed  # noqa: E402

KNOWN = "NSE_FO:44624"
UNKNOWN = "NSE_FO:99999999"
ITEMS = {f"{i.contract.exchange_segment}:{i.contract.exchange_token}": i for i in listed()}


def _body(*ids):
    return {"underlying": "NIFTY",
            "legs": [{"instrument_id": i, "action": "SELL", "lots": 1, "planned_entry": "100.00",
                      "captured_at": "2026-10-08T09:20:09+05:30"} for i in ids]}


async def _answer(lookup, *ids):
    from ofo_app.main import create_app
    from ofo_app.routes.outcome import get_contract_lookup

    app = create_app()
    app.dependency_overrides[get_contract_lookup] = lambda: lookup
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/strategies/outcome", json=_body(*ids))
    assert res.status_code == 200, res.text
    return res.json()


async def _from_store(ids):
    return {i: ITEMS[i] for i in dict.fromkeys(ids) if i in ITEMS}


async def test_a_known_contract_is_named_and_an_unknown_one_stays_unnamed():
    """AC-3: both branches in one answer."""
    out = await _answer(_from_store, KNOWN, UNKNOWN)
    assert out["state"] == "NOT_CONNECTED"
    known, unknown = out["legs"]
    c = ITEMS[KNOWN].contract
    assert (known["instrument"], known["strike"], known["expiry"]) == (c.instrument_type, f"{c.strike:f}", c.expiry.isoformat())
    assert known["instrument"] in ("CE", "PE")
    assert (unknown["instrument"], unknown["strike"], unknown["expiry"], unknown["symbol"]) == (None, None, None, None)


async def test_a_catalogue_that_cannot_be_read_still_answers_with_unnamed_legs(monkeypatch):
    """AC-3: the real lookup, with the database session maker raising (whatever DATABASE_URL is), fails soft: the state
    must always answer (#259 item 3: the test no longer depends on the environment having no database)."""
    from ofo_app import db
    from ofo_app.main import create_app

    def broken():
        raise RuntimeError("catalogue host unreachable")

    monkeypatch.setattr(db, "get_sessionmaker", broken)
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as ac:
        res = await ac.post("/api/strategies/outcome", json=_body(KNOWN))
    assert res.status_code == 200, res.text
    leg = res.json()["legs"][0]
    assert (res.json()["state"], leg["instrument"], leg["expiry"]) == ("NOT_CONNECTED", None, None)


async def test_the_lookup_is_not_called_when_a_provider_exists():
    """AC-3: the catalogue is read only on the no-provider path."""
    from ofo_app.routes.outcome import get_stored_legs

    called = []

    async def lookup(ids):
        called.append(ids)
        return {}

    ctx = object()
    assert await get_stored_legs(_Req(KNOWN), ctx, lookup) is None
    assert called == []
    assert await get_stored_legs(_Req(KNOWN), None, lookup) == {} and called == [[KNOWN]]


class _Req:
    def __init__(self, *ids):
        self.legs = [type("L", (), {"instrument_id": i}) for i in ids]


async def test_the_socket_answer_names_legs_exactly_like_the_rest_answer_with_no_provider():
    """#259 item 1: one answer, two delivery paths: the same draft with no provider carries the same leg names."""
    import asyncio
    import json

    from ofo_app.errors import socket_body
    from ofo_app.live_push import StrategyPush
    from ofo_app.routes.outcome import OutcomeResponse

    rest = await _answer(_from_store, KNOWN, UNKNOWN)

    class Channel:
        def __init__(self):
            self.sent, self.inbound = [], asyncio.Queue()

        async def receive(self):
            return await self.inbound.get()

        async def send(self, source):
            self.sent.append(json.loads(bytes(socket_body(source, (OutcomeResponse,)))))

    channel = Channel()
    push = StrategyPush(channel, None, monotonic=lambda: 1000.0, poll=0.005, lookup=_from_store)
    task = asyncio.create_task(push.run())
    await channel.inbound.put(_body(KNOWN, UNKNOWN))
    for _ in range(20):
        await asyncio.sleep(0.01)
    task.cancel()
    assert len(channel.sent) == 1 and channel.sent[0]["state"] == "NOT_CONNECTED"
    assert channel.sent[0]["legs"] == rest["legs"]
    assert channel.sent[0]["legs"][0]["instrument"] in ("CE", "PE")


async def test_a_catalogue_read_that_never_returns_is_cut_off_and_the_answer_comes_back(monkeypatch):
    """#259 item 2: a hanging catalogue read must not hang the not-connected answer; the legs stay unnamed."""
    import asyncio

    from ofo_app.routes import outcome

    monkeypatch.setattr(outcome, "CATALOGUE_READ_TIMEOUT_SECONDS", 0.05)

    async def never(_ids):
        await asyncio.Event().wait()

    out = await asyncio.wait_for(_answer(never, KNOWN), timeout=5)
    leg = out["legs"][0]
    assert (out["state"], leg["instrument"], leg["expiry"]) == ("NOT_CONNECTED", None, None)
