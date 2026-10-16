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
import copy
import dataclasses
import datetime
import json
import pickle
from types import SimpleNamespace
from decimal import Decimal as D
from pathlib import Path

import pytest
from execution_inputs import IST, all_true_context, check
from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.execution import CheckCode
from ofo.instruments import NSE_FO, Catalogue, EligibilityStatus, InstrumentId, ZerodhaEligibility
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


def _registry(today: datetime.date = TODAY, *, refusals=None, refused_at=None) -> ZerodhaEligibility:
    states = el.states_from_parsed_list([e.contract for e in _catalogue().all_entries()], LIST_ROWS)
    minted = el.registry_from_list(states, today=today, loaded_at=LOADED_AT)
    return minted if refusals is None else el.apply_margin_refusals(minted, refusals, refused_at=refused_at)


def _row(**flags) -> SimpleNamespace:
    """One synthetic store row (the columns ``list_state_from_row`` reads) for the core contract."""
    base = dict(exchange_segment=NSE_FO, exchange_token=47189, instrument_type="CE",
                expiry=datetime.date(2026, 10, 19), currently_listed=True, retired=False, delisted=False,
                has_zerodha_row=True)
    return SimpleNamespace(**(base | flags))


def _leg(strike: str) -> Leg:
    return Leg(Action.BUY, Instrument.CE, D(strike), datetime.date(2026, 10, 19), 65, D("40.00"))


def _gate(leg: Leg, registry: object):
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
    ({"currently_listed": False}, el.REASON_NOT_IN_LIST),
    ({"expiry": None}, el.REASON_NO_EXPIRY),
    ({"instrument_type": "INDEX", "expiry": None}, el.REASON_INDEX),
])
def test_every_lifecycle_refusal_has_its_reason(flags, reason):
    status = el.status_from_list(el.list_state_from_row(_row(**flags)), today=TODAY, loaded_at=LOADED_AT)
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
    with pytest.raises(TypeError):
        el.apply_margin_refusals(_registry(), {(NSE_FO, 47189): "x"}, refused_at=LOADED_AT)  # not an InstrumentId


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
    state = el.list_state_from_row(_row())
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


# ---------------------------------------------------------------------------------------------------------------
# W-092 round 2 (Tier A review MAJOR: forgeable eligibility; findings caller-supplied-verdict-trusted,
# sealed-object-mutable-after-seal). The gate trusts only the sealed ZerodhaEligibility minted from list rows.
# ---------------------------------------------------------------------------------------------------------------

UNCONFIRMED = "has not been confirmed as available on Zerodha yet"


def _refused_as_unconfirmed(registry: object) -> None:
    result = _gate(_leg("23650"), registry)
    assert [f.code for f in result.failures] == [CheckCode.CONTRACT_NOT_ELIGIBLE]
    assert UNCONFIRMED in result.failures[0].reason


class _HandMade:
    """A1: a hand-made registry that says the core contract is tradable (the old open registry's shape)."""

    def get(self, instrument_id):
        return EligibilityStatus(instrument_id, True, LOADED_AT)

    def is_tradable(self, instrument_id):
        return True


def test_a1_a_hand_made_registry_is_refused_by_the_gate():
    with pytest.raises(TypeError):
        ZerodhaEligibility(((NSE_FO, 47189, True, LOADED_AT, None),))  # the class cannot be called
    _refused_as_unconfirmed(_HandMade())
    _refused_as_unconfirmed(((NSE_FO, 47189, True, LOADED_AT, None),))  # a plain tuple of entries
    _refused_as_unconfirmed(None)


def test_a1b_a_margin_refusal_cannot_be_overwritten_to_tradable():
    key = InstrumentId(NSE_FO, 47189)
    refused = _registry(refusals={key: "Margin validation failed"}, refused_at=LOADED_AT)
    assert not hasattr(refused, "record")
    with pytest.raises((AttributeError, TypeError)):
        object.__setattr__(refused, "_status", {})
    with pytest.raises(TypeError):
        refused[0] = (NSE_FO, 47189, True, LOADED_AT, None)  # type: ignore[index]
    status = refused.get(CORE_ID)
    object.__setattr__(status, "tradable", True)  # the returned status is a copy: editing it changes nothing
    object.__setattr__(key, "exchange_token", 47185)  # nor does editing the refusal's key afterwards
    assert refused.is_tradable(CORE_ID) is False
    assert CheckCode.CONTRACT_NOT_ELIGIBLE in _gate(_leg("23650"), refused).failed_codes
    assert _registry().is_tradable(CORE_ID)  # a new registry from the list is unaffected


def test_a1c_a_hand_made_contract_state_is_refused():
    with pytest.raises(TypeError):
        el.ListState(CORE_ID, "CE", datetime.date(2026, 10, 19), True)
    for forged in [SimpleNamespace(instrument_id=CORE_ID, instrument_type="CE", expiry=datetime.date(2026, 10, 19),
                                   listed=True, retired=False, delisted=False, has_zerodha_row=True),
                   (NSE_FO, 47189, "CE", datetime.date(2026, 10, 19), True, False, False, True)]:
        with pytest.raises(TypeError):
            el.status_from_list(forged, today=TODAY, loaded_at=LOADED_AT)
        with pytest.raises(TypeError):
            el.registry_from_list([forged], today=TODAY, loaded_at=LOADED_AT)


@pytest.mark.parametrize("value", ["true", 1, None])
def test_a_row_flag_that_is_not_a_bool_is_refused(value):
    with pytest.raises(TypeError):
        el.list_state_from_row(_row(currently_listed=value))


def _sealed_objects():
    return [_registry(), el.list_state_from_row(_row())]


@pytest.mark.parametrize("attack", [
    copy.copy, copy.deepcopy, pickle.dumps,
    lambda o: dataclasses.replace(o),
    lambda o: object.__setattr__(o, "x", 1),
], ids=["copy", "deepcopy", "pickle", "replace", "setattr"])
def test_the_sealed_objects_cannot_be_copied_pickled_replaced_or_written(attack):
    for sealed in _sealed_objects():
        with pytest.raises((TypeError, AttributeError)):
            attack(sealed)


def test_the_sealed_types_cannot_be_subclassed():
    for sealed_type in (ZerodhaEligibility, el.ListState):
        with pytest.raises(TypeError):
            type("Sub", (sealed_type,), {})


def test_a_tuple_carrying_real_entries_is_not_the_sealed_type():
    """The gate compares the exact type: a plain tuple holding a minted object's own entries is refused."""
    minted = _registry()
    _refused_as_unconfirmed(tuple(minted))
    assert not _gate(_leg("23650"), minted).blocked


def test_only_the_eligibility_modules_mint_eligibility():
    """Product code mints eligibility only in the domain module and the app's store reader (no other product caller
    can feed the gate a registry it built itself)."""
    backend = Path(el.__file__).resolve().parents[2]
    allowed = {"ofo/instruments/eligibility.py", "ofo_app/eligibility_from_zerodha.py"}
    minting = {"registry_from_list", "apply_margin_refusals", "list_state_from_row", "states_from_parsed_list"}
    users = set()
    for path in backend.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        if names & minting:
            users.add(path.relative_to(backend).as_posix())
    assert users == allowed
