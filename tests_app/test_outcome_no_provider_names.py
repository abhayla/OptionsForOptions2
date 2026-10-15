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


async def test_a_catalogue_that_cannot_be_read_still_answers_with_unnamed_legs():
    """AC-3: the real lookup with no database configured fails soft (the state must always answer)."""
    from ofo_app.main import create_app

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
