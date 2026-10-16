"""W-092 core proof (ADR-104, REQ-053 AC-3): eligibility filled from Zerodha's own instrument list lets a real contract
through the existing pre-execution gate, and refuses one the list does not carry. No database.

Real input: tests/fixtures/eligibility/instruments-2026-10-16-slice.json, rows copied verbatim from the recorder's
2026-10-16 copy of Zerodha's list (NIFTY 23600 CE/PE, 23650 CE/PE of 2026-10-19; Zerodha tokens 12079874, 12080130,
12080386, 12083202). The core contract is the NIFTY 23650 CE (Zerodha token 12080386, NSE token 47189). The contract
the catalogue holds but the list slice does not carry is the NIFTY 23550 CE (NSE token 47185). Symbols are read from
the fixture, never typed here.

Spec basis (quoted): REQ-053 AC-3 "Before a leg is added, the builder checks what Zerodha data allows and blocks legs
that are currently unavailable; the check repeats just before execution."; AC-2 "The contract catalogue (what exists)
is stored separately from current eligibility (what Zerodha permits)"; AC-4 "The platform does not re-implement
Zerodha's RMS rules."
"""
from __future__ import annotations

import ast
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from execution_inputs import IST, all_true_context, check
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import CheckCode
from ofo.instruments import Catalogue, EligibilityRegistry, InstrumentId, NSE_FO
from ofo.instruments import eligibility as el
from ofo.instruments.parser import zerodha_listed

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "eligibility" / "instruments-2026-10-16-slice.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"), parse_float=D)
LOADED_AT = datetime.datetime.fromisoformat(DATA["list_loaded_at"])
AS_OF = datetime.datetime(2026, 10, 16, 12, 30, tzinfo=IST)  # the recorded day, during market hours
TODAY = AS_OF.date()
CORE_ZERODHA_TOKEN = "12080386"
ABSENT_ZERODHA_TOKEN = "12079362"
TICK = D("0.05")  # every NFO option row of Zerodha's list (the fixture's tick_size note)


def _listed(zerodha_token: str, row: dict):
    """One recorder row as Zerodha's list row (exchange token = instrument_token >> 8, the fixture's checked rule)."""
    return zerodha_listed(
        instrument_token=int(zerodha_token), exchange_token=int(zerodha_token) >> 8, tradingsymbol=row["symbol"],
        name=row["group"].split()[0], expiry=datetime.date.fromisoformat(row["expiry"]), strike=D(row["strike"]),
        tick_size=TICK, lot_size=int(row["lot"]), instrument_type=row["type"], segment="NFO-OPT", exchange="NFO")


LIST_ROWS = [_listed(t, r) for t, r in DATA["list"].items()]
ABSENT_ROW = _listed(ABSENT_ZERODHA_TOKEN, DATA["catalogue_only"][ABSENT_ZERODHA_TOKEN])
CORE_ID = InstrumentId(NSE_FO, 47189)
ABSENT_ID = InstrumentId(NSE_FO, 47185)


def _catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load([*LIST_ROWS, ABSENT_ROW])  # what exists: the day's rows plus a contract stored by an earlier load
    return cat


def _registry(today: datetime.date = TODAY, **kw) -> EligibilityRegistry:
    states = el.states_from_parsed_list([e.contract for e in _catalogue().all_entries()], LIST_ROWS)
    return el.registry_from_list(states, today=today, loaded_at=LOADED_AT, **kw)


def _leg(strike: str) -> Leg:
    return Leg(Action.BUY, Instrument.CE, D(strike), datetime.date(2026, 10, 19), 65, D("40.00"))


def _gate(leg: Leg, registry: EligibilityRegistry):
    return check(Strategy((leg,)), all_true_context(as_of=AS_OF), _catalogue(), registry)


def test_the_fixture_is_the_real_core_row():
    row = DATA["list"][CORE_ZERODHA_TOKEN]
    assert (row["type"], row["strike"], row["expiry"], row["lot"]) == ("CE", "23650.00", "2026-10-19", 65)
    assert CORE_ID == LIST_ROWS[[r.ref("zerodha").broker_token for r in LIST_ROWS].index(CORE_ZERODHA_TOKEN)].id


def test_core_the_listed_contract_is_tradable_and_passes_the_real_gate():
    registry = _registry()
    status = registry.get(CORE_ID)
    assert (status.tradable, status.checked_at, status.reason) == (True, LOADED_AT, None)
    result = _gate(_leg("23650"), registry)
    assert CheckCode.CONTRACT_NOT_ELIGIBLE in result.passed
    assert not result.blocked, [f.text for f in result.failures]


def test_core_a_contract_not_in_the_list_is_not_tradable_and_the_gate_says_unavailable():
    registry = _registry()
    status = registry.get(ABSENT_ID)
    assert (status.tradable, status.reason) == (False, el.REASON_NOT_IN_LIST)
    result = _gate(_leg("23550"), registry)
    assert [f.code for f in result.failures] == [CheckCode.CONTRACT_NOT_ELIGIBLE]
    assert result.failures[0].reason == (
        "Leg 1 (BUY NIFTY 23,550 CE, expiry 19 Oct 2026) is currently unavailable on Zerodha. Zerodha isn't accepting "
        "fresh orders for this contract right now. Strikes you could consider instead: 23,600.00 or 23,650.00. Your "
        "strategy has not been changed.")


def test_expired_is_not_tradable_even_when_the_list_still_carries_it():
    """F-33: expired rows stay in the list (398 SENSEX rows on 08-Oct at 16:30)."""
    after = datetime.date(2026, 10, 20)
    assert _registry(after).get(CORE_ID).reason == el.REASON_EXPIRED
    assert _registry(datetime.date(2026, 10, 19)).is_tradable(CORE_ID)  # the expiry day itself is still tradable


@pytest.mark.parametrize("flags, reason", [
    ({"delisted": True}, el.REASON_DELISTED),
    ({"retired": True}, el.REASON_RETIRED),
    ({"has_zerodha_row": False}, el.REASON_NO_ZERODHA_ROW),
    ({"listed": False}, el.REASON_NOT_IN_LIST),
    ({"expiry": None}, el.REASON_NO_EXPIRY),
    ({"instrument_type": "INDEX", "expiry": None}, el.REASON_INDEX),
])
def test_every_lifecycle_refusal_has_its_reason(flags, reason):
    base = dict(instrument_id=CORE_ID, instrument_type="CE", expiry=datetime.date(2026, 10, 19), listed=True)
    status = el.status_from_list(el.ListState(**(base | flags)), today=TODAY, loaded_at=LOADED_AT)
    assert (status.tradable, status.reason) == (False, reason)


def test_a_margin_reply_refusal_makes_the_leg_not_tradable_with_zerodhas_text():
    text = "Margin validation failed for this order"  # the text is carried verbatim, whatever Zerodha says
    at = datetime.datetime(2026, 10, 16, 12, 31, tzinfo=IST)
    registry = _registry(refusals={CORE_ID: text}, refused_at=at)
    status = registry.get(CORE_ID)
    assert (status.tradable, status.reason, status.checked_at) == (False, text, at)
    assert CheckCode.CONTRACT_NOT_ELIGIBLE in _gate(_leg("23650"), registry).failed_codes


def test_a_refusal_never_makes_a_contract_tradable():
    unknown = InstrumentId(NSE_FO, 99_999_999)
    registry = _registry(refusals={unknown: "x"}, refused_at=LOADED_AT)
    assert registry.get(unknown).tradable is False
    with pytest.raises(ValueError):
        _registry(refusals={CORE_ID: "  "}, refused_at=LOADED_AT)  # no text = not Zerodha's answer
    with pytest.raises(TypeError):
        _registry(refusals={CORE_ID: "x"})  # a refusal without its time


def test_a_list_row_the_catalogue_does_not_hold_is_never_added():
    """AC-2: eligibility never adds a contract; a row only in the list gets no status (the gate: not found)."""
    states = el.states_from_parsed_list([ABSENT_ROW.contract], LIST_ROWS)
    registry = el.registry_from_list(states, today=TODAY, loaded_at=LOADED_AT)
    assert registry.get(CORE_ID) is None and registry.get(ABSENT_ID).tradable is False


def test_the_clock_inputs_fail_closed():
    with pytest.raises(TypeError):
        el.registry_from_list([], today=AS_OF, loaded_at=LOADED_AT)  # a datetime is not the India date
    with pytest.raises(TypeError):
        el.registry_from_list([], today=TODAY, loaded_at=datetime.datetime(2026, 10, 16, 12, 7))  # noqa: DTZ001 - naive on purpose
    state = el.ListState(CORE_ID, "CE", datetime.date(2026, 10, 19), True)
    with pytest.raises(ValueError):
        el.registry_from_list([state, state], today=TODAY, loaded_at=LOADED_AT)


def test_the_registry_has_no_path_that_writes_into_the_catalogue():
    """AC-2: the eligibility module imports no catalogue and calls none of its write methods."""
    tree = ast.parse(Path(el.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
    imported |= {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"Catalogue", "CatalogueEntry", "ofo.instruments.catalogue"}, imported
    called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not called & {"load", "update", "apply_update", "mark_unlisted"}, called
