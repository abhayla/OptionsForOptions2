"""W-118-sel part 2 (REQ-030 AC-13, AC-16; ADR-132 (3), ADR-104): the chain read says, per contract, whether Zerodha
permits it and why not.

Core proof: the recorded 2026-10-16 replay of Zerodha's list
(tests/fixtures/eligibility/instruments-2026-10-16-slice.json) goes through the real eligibility functions into the
real chain answer. A listed contract is permitted; the contract the catalogue holds but today's list does not carry is
`not_listed`; a margin-refused strike is `restricted`; no eligibility answer at all is `unknown`.

Spec basis (quoted): REQ-030 AC-16 "A contract Zerodha currently won't accept stays visible, shows 'Currently
unavailable on Zerodha' with a plain reason, cannot be added..."; ADR-132 (3) the three reason lines; ADR-016 (Zerodha
is the authority). Findings checked: caller-supplied-verdict-trusted (the verdict is built on the server from the
sealed eligibility reads, never taken from the browser), guard-as-forbidden-list (permitted ONLY on an explicit
tradable True; every other shape is not permitted).
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.instruments import NSE_FO, Catalogue
from ofo.instruments import eligibility as el
from ofo.instruments.models import InstrumentId
from ofo.instruments.parser import zerodha_listed
from ofo.marketdata.fanout import FanOut
from ofo.money import PAISE
from ofo_app import chain_push
from ofo_app.catalogue_picker import PickableContract
from ofo_app.chain_push import ChainCatalogue, ChainRequest, permission_of, permissions_for
from ofo_app.routes.chain import chain_read
from ofo_app.routes.outcome import MarketContext
from test_chain_live import (
    HTTP_OK,
    T0,
    Clock,
    FakeProvider,
    _app_client,
    close,
    index_quote,
    make_rig,
    option_quote,
    settle,
    start,
)

FIXTURE = (Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "eligibility"
           / "instruments-2026-10-16-slice.json")
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"), parse_float=D)
LOADED_AT = datetime.datetime.fromisoformat(DATA["list_loaded_at"])
TODAY = datetime.date(2026, 10, 16)  # the recorded day
EXPIRY = datetime.date(2026, 10, 19)
TICK = D("0.05")
ONE, TWO, FOUR, FIVE = 1, 2, 4, 5


def _listed(token: str, row: dict):
    return zerodha_listed(
        instrument_token=int(token), exchange_token=int(token) >> 8, tradingsymbol=row["symbol"],
        name=row["group"].split()[0], expiry=datetime.date.fromisoformat(row["expiry"]), strike=D(row["strike"]),
        tick_size=TICK, lot_size=int(row["lot"]), instrument_type=row["type"], segment="NFO-OPT", exchange="NFO")


LIST_ROWS = [_listed(t, r) for t, r in DATA["list"].items()]
ABSENT_TOKEN = next(iter(DATA["catalogue_only"]))
ABSENT_ROW = _listed(ABSENT_TOKEN, DATA["catalogue_only"][ABSENT_TOKEN])
ALL_ROWS = [*LIST_ROWS, ABSENT_ROW]  # what the catalogue holds: the day's rows plus the one the list does not carry


def _pickables() -> tuple[PickableContract, ...]:
    out = []
    for n, row in enumerate(sorted(ALL_ROWS, key=lambda r: (r.contract.strike, r.contract.instrument_type))):
        c = row.contract
        out.append(PickableContract(
            contract_id=n + 1, instrument_id=f"{NSE_FO}:{row.id.exchange_token}", exchange_segment=NSE_FO,
            exchange_token=row.id.exchange_token, instrument_type=c.instrument_type, expiry=c.expiry, strike=c.strike,
            lot_size=65, symbol=row.ref("zerodha").broker_symbol))
    return tuple(out)


CONTRACTS = _pickables()
BY_STRIKE_SIDE = {(c.strike, c.instrument_type): c for c in CONTRACTS}
LISTED_CE = BY_STRIKE_SIDE[(D("23650"), "CE")]  # the W-092 core contract (NSE token 47189)
ABSENT_CE = BY_STRIKE_SIDE[(D("23550"), "CE")]  # NSE token 47185: held by the catalogue, not carried by the list
RESTRICTED_PE = BY_STRIKE_SIDE[(D("23600"), "PE")]


def _registry(*, refusals=None):
    cat = Catalogue()
    cat.load(ALL_ROWS)
    states = el.states_from_parsed_list([e.contract for e in cat.all_entries()], LIST_ROWS)
    minted = el.registry_from_list(states, today=TODAY, loaded_at=LOADED_AT)
    if refusals is None:
        return minted
    return el.apply_margin_refusals(minted, refusals, refused_at=LOADED_AT)


def _statuses(registry) -> list:
    return [registry.get(InstrumentId(c.exchange_segment, c.exchange_token)) for c in CONTRACTS]


def _catalogue(permissions) -> ChainCatalogue:
    return ChainCatalogue(expiries=(EXPIRY,), contracts=CONTRACTS, permissions=permissions)


def _live_provider() -> FakeProvider:
    provider = FakeProvider()
    provider.tick(index_quote("23620.00"))
    for c in CONTRACTS:
        provider.tick(option_quote(c.instrument_id, "100.00", contracts=CONTRACTS))
    return provider


def _cells(body) -> dict:
    return {c.instrument_id: c for row in body.rows for c in (row.ce, row.pe) if c is not None}


def _read(permissions, provider=None):
    provider = provider or _live_provider()
    ctx = MarketContext(provider, Clock(T0), D("0.065"))
    fanout = FanOut(provider)
    streaming = lambda i: fanout.subscriber_count(i) > 0  # noqa: E731
    streaming.ctx = ctx
    req = ChainRequest(underlying="NIFTY", expiry=EXPIRY, strikes_each_side=2)
    return chain_read(ctx, None, req, _catalogue(permissions), fallback=False, now=Clock(T0)), streaming


def test_the_fixture_is_the_recorded_replay():
    """The inputs are the recorded 2026-10-16 rows, not typed shapes: 4 listed rows and the one catalogue-only row."""
    assert len(LIST_ROWS) == FOUR and (LISTED_CE.exchange_token, ABSENT_CE.exchange_token) == (47189, 47185)
    assert len(CONTRACTS) == FIVE


def test_core_replay_listed_not_listed_restricted_and_unknown_per_cell():
    """Core: through the real eligibility functions, the chain answer marks the listed contract permitted, the
    list-absent one `not_listed`, a margin-refused one `restricted`; a contract with no eligibility answer is
    `unknown`. Only the first is permitted."""
    refusals = {InstrumentId(RESTRICTED_PE.exchange_segment, RESTRICTED_PE.exchange_token): "Margin not allowed"}
    permissions = permissions_for(CONTRACTS, _statuses(_registry(refusals=refusals)))
    del permissions[next(c.instrument_id for c in CONTRACTS if (c.strike, c.instrument_type) == (D("23650"), "PE"))]
    body, _ = _read(permissions)
    cells = _cells(body)
    got = {(c.instrument_id): (c.permitted, c.unavailable_reason) for c in cells.values()}
    assert got[LISTED_CE.instrument_id] == (True, None)
    assert got[ABSENT_CE.instrument_id] == (False, "not_listed")
    assert got[RESTRICTED_PE.instrument_id] == (False, "restricted")
    unknown_id = next(c.instrument_id for c in CONTRACTS if (c.strike, c.instrument_type) == (D("23650"), "PE"))
    assert got[unknown_id] == (False, "unknown")
    assert {i for i, (p, _r) in got.items() if p} == {
        LISTED_CE.instrument_id, BY_STRIKE_SIDE[(D("23600"), "CE")].instrument_id}


def test_the_rest_route_carries_the_verdict_for_the_browser():
    """The same answer over GET /api/market/chain: `permitted` (bool) and `unavailable_reason` on every cell."""
    permissions = permissions_for(CONTRACTS, _statuses(_registry()))

    async def reader(_underlying, _expiry):
        return _catalogue(permissions)

    client = _app_client(MarketContext(_live_provider(), Clock(T0), D("0.065")), reader)
    res = client.get("/api/market/chain", params={"underlying": "NIFTY", "expiry": EXPIRY.isoformat(),
                                                  "strikes_each_side": 2})
    assert res.status_code == HTTP_OK, res.text
    cells = {c["instrument_id"]: c for row in res.json()["rows"] for c in (row["ce"], row["pe"]) if c}
    listed = cells[LISTED_CE.instrument_id]
    assert (listed["permitted"], listed["unavailable_reason"]) == (True, None)
    absent = cells[ABSENT_CE.instrument_id]
    assert (absent["permitted"], absent["unavailable_reason"]) == (False, "not_listed")


# ---- every answer state of eligibility (the table in the report): one test each -------------------------------------


def _status(tradable, reason=None):
    return el.EligibilityStatus(InstrumentId(NSE_FO, 1), tradable, LOADED_AT, reason)


def test_state_permitted_tradable_true():
    assert permission_of(_status(True)) == "permitted"


@pytest.mark.parametrize("reason", [el.REASON_NOT_IN_LIST, el.REASON_EXPIRED, el.REASON_DELISTED, el.REASON_RETIRED,
                                    el.REASON_NO_ZERODHA_ROW, el.REASON_INDEX, el.REASON_NO_EXPIRY])
def test_state_not_listed_every_list_reason(reason):
    assert permission_of(_status(False, reason)) == "not_listed"


@pytest.mark.parametrize("text", ["Margin not allowed", "RMS: scrip blocked", "anything else Zerodha says"])
def test_state_restricted_any_other_refusal_text(text):
    assert permission_of(_status(False, text)) == "restricted"


def test_state_unknown_no_status_at_all():
    """No load ever / no row: no status -> left out of the map -> the cell reads unknown, never permitted."""
    assert permission_of(None) is None
    assert permissions_for(CONTRACTS, [None] * len(CONTRACTS)) == {}
    body, _ = _read({})
    assert {(c.permitted, c.unavailable_reason) for c in _cells(body).values()} == {(False, "unknown")}


@pytest.mark.parametrize("truthy", [1, "yes", "True", object()])
def test_state_a_truthy_but_not_true_tradable_is_never_permitted(truthy):
    """Guard: permitted only on `tradable is True` (dies if the check becomes `if status.tradable`)."""
    assert permission_of(_status(truthy, el.REASON_NOT_IN_LIST)) != "permitted"
    assert permission_of(_status(truthy)) != "permitted"


@pytest.mark.parametrize("forged", ["PERMITTED", "ok", True, 1, None, ""])
def test_state_a_forged_map_value_reads_unknown_not_permitted(forged):
    """Guard: only the exact string "permitted" opens a cell; any other value in the map reads unknown."""
    body, _ = _read({c.instrument_id: forged for c in CONTRACTS})
    assert {(c.permitted, c.unavailable_reason) for c in _cells(body).values()} == {(False, "unknown")}


def test_state_failed_the_eligibility_read_raises_all_unknown(monkeypatch):
    """The eligibility read itself failing (database error): no error, no guessed permission - every cell unknown."""
    import asyncio  # noqa: PLC0415

    from ofo_app import eligibility_from_zerodha  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    async def boom(*_a, **_k):
        raise SQLAlchemyError("down")

    monkeypatch.setattr(eligibility_from_zerodha, "leg_statuses", boom)
    assert asyncio.run(chain_push._read_permissions(object(), CONTRACTS, TODAY)) == {}


def test_state_empty_no_contracts_means_no_cells():
    assert permissions_for((), []) == {}


# ---- refresh: the same request again re-reads the catalogue and its eligibility -------------------------------------


async def test_a_repeated_request_is_a_refresh_that_re_reads_the_catalogue():
    """AC-16 "can be refreshed": the screen re-sends its current request; the server re-reads (once a second at most),
    so a contract whose eligibility came back shows as permitted on the next push. Dies if a repeated request is
    dropped as 'unchanged'."""
    calls = []

    class FlipReader:
        async def __call__(self, underlying, expiry):
            calls.append(expiry)
            permissions = {} if len(calls) == ONE else permissions_for(CONTRACTS, _statuses(_registry()))
            return _catalogue(permissions)

    _provider, _feed, channel, mono, push = make_rig(FlipReader(), _live_provider())
    req = {"underlying": "NIFTY", "expiry": EXPIRY.isoformat(), "strikes_each_side": 2}
    task = await start(push, channel, req)
    first = channel.sent[-1]
    await channel.inbound.put(req)
    mono.now += 1.0
    await settle()
    await close(channel, task)
    assert len(calls) == TWO
    cell = lambda body: next(c for row in body["rows"] for c in (row["ce"], row["pe"])  # noqa: E731
                             if c and c["instrument_id"] == LISTED_CE.instrument_id)
    assert (cell(first)["permitted"], cell(first)["unavailable_reason"]) == (False, "unknown")
    assert (cell(channel.sent[-1])["permitted"], cell(channel.sent[-1])["unavailable_reason"]) == (True, None)


def test_money_unchanged_by_the_permission_fields():
    """The new fields do not touch prices: the listed cell's LTP is still the 2-decimal string as given."""
    body, _ = _read(permissions_for(CONTRACTS, _statuses(_registry())))
    assert _cells(body)[LISTED_CE.instrument_id].ltp == D("100.00").quantize(PAISE)
