"""W-061 / REQ-038 AC-5: the stored form of a strategy definition round-trips exactly and refuses anything else.

Spec basis: REQ-038 AC-5 ("load back exactly as saved; live prices are never saved inside the strategy"); AC-1 (the
definition and the live state are separate objects); ADR-008 (Decimal, never float); ADR-016 (no silent contract
substitution).

Real rows (tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv, Zerodha's instrument list of 2026-10-08):
NIFTY 22800 CE (NFO exchange token 44624), 23000 CE (44632), 22400 PE (44604) and 22200 PE (44595), expiry
2026-10-13, lot 65 (trading symbols are in the database test; the tests/ symbol guard checks an older slice). The internal contract ids (101..104) are MODELLED: they are
whatever the catalogue's sequence assigns, and the database test uses the real ones.
Standard library only (tests/ never imports app packages).
"""
from __future__ import annotations

import dataclasses
import datetime
import json
from decimal import Decimal

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.strategy import live_state
from ofo.strategy import stored_form as sf

EXPIRY = datetime.date(2026, 10, 13)
LOT = 65
#: internal id -> (instrument, strike) for the real 13-Oct-2026 contracts
CATALOGUE = {
    101: (Instrument.CE, Decimal("22800")),
    102: (Instrument.CE, Decimal("23000")),
    103: (Instrument.PE, Decimal("22400")),
    104: (Instrument.PE, Decimal("22200")),
}


def _resolve(catalogue=CATALOGUE, live=True):
    def resolve(contract_id):
        if contract_id not in catalogue:
            return None
        instrument, strike = catalogue[contract_id]
        return sf.CatalogueTerms("NIFTY", instrument, strike, EXPIRY, LOT, live)
    return resolve


IRON_CONDOR = [sf.LegChoice(101, Action.SELL, LOT), sf.LegChoice(102, Action.BUY, LOT),
               sf.LegChoice(103, Action.SELL, LOT), sf.LegChoice(104, Action.BUY, LOT)]


def _iron_condor(**fields):
    return sf.build_from_catalogue("NIFTY", IRON_CONDOR, _resolve(), **fields)


FILLED = dict(rules_ref="exit-rules-1", risk_limits={"max_loss": Decimal("5000.50"), "max_lots": Decimal("2")},
              preferences={"display": "compact"})


@pytest.mark.parametrize("fields", [{}, FILLED], ids=["plain", "rules-limits-preferences"])
def test_ac5_round_trip_is_exact(fields):
    saved = _iron_condor(**fields)
    text = sf.dumps(saved)
    back = sf.loads(text, _resolve())
    assert back == saved
    assert sf.dumps(back) == text
    assert [str(leg.strike) for leg in back.definition.legs] == ["22800", "23000", "22400", "22200"]
    assert [leg.quantity for leg in back.definition.legs] == [65, 65, 65, 65]
    assert back.contract_ids == (101, 102, 103, 104)
    if fields:
        assert back.definition.risk_limits == (("max_loss", Decimal("5000.50")), ("max_lots", Decimal("2")))
        assert str(dict(back.definition.risk_limits)["max_loss"]) == "5000.50"  # the text form survives
        assert back.definition.preferences == (("display", "compact"),)
        assert back.definition.rules_ref == "exit-rules-1"


def test_ac5_stored_text_has_decimal_strings_and_no_float():
    doc = json.loads(sf.dumps(_iron_condor(**FILLED)))
    assert [leg["strike"] for leg in doc["legs"]] == ["22800", "23000", "22400", "22200"]
    assert doc["risk_limits"] == {"max_loss": "5000.50", "max_lots": "2"}

    def numbers(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                yield from numbers(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from numbers(v)
        elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
            yield obj
    assert all(isinstance(n, int) for n in numbers(doc))


def _live_state_names() -> set[str]:
    names = set()
    for cls in (live_state.LiveState, live_state.LegQuote, live_state.Greeks):
        names |= {f.name for f in dataclasses.fields(cls)}
    return names - {"leg_index"}


def test_ac5_the_form_holds_no_live_state_name():
    """AC-1/AC-5: the form's keys are a closed set that shares no name with LiveState, LegQuote or Greeks."""
    live = _live_state_names()
    assert {"ltp", "bid", "ask", "iv", "pnl", "margin", "spot", "delta"} <= live
    doc = json.loads(sf.dumps(_iron_condor(**FILLED)))
    keys = set(doc) | {k for leg in doc["legs"] for k in leg}
    assert keys == sf.DOCUMENT_KEYS | sf.LEG_KEYS
    assert not keys & live


def _doc(**changes):
    doc = json.loads(sf.dumps(_iron_condor()))
    doc.update(changes)
    return doc


def _leg_doc(**changes):
    doc = _doc()
    doc["legs"][0].update(changes)
    return doc


@pytest.mark.parametrize("text, code", [
    (sf.dumps(_iron_condor()).replace('"22800"', "22800.0"), sf.NOT_DECIMAL_STRING),  # float strike (mutation 1)
    (sf.dumps(_iron_condor()).replace('"22800"', "22800"), sf.NOT_DECIMAL_STRING),  # integer strike
    (sf.dumps(_iron_condor()).replace('"22800"', '"NaN"'), sf.NOT_DECIMAL_STRING),
    ("{", sf.MALFORMED),
    ('"a string"', sf.MALFORMED),
    ('{"schema_version":1,"schema_version":1}', sf.MALFORMED),
    ("[1]", sf.MALFORMED),
])
def test_ac5_malformed_or_float_text_is_refused(text, code):
    with pytest.raises(sf.StoredFormError) as err:
        sf.loads(text, _resolve())
    assert err.value.code == code


@pytest.mark.parametrize("doc, code", [
    (_doc(ltp="101.5"), sf.UNKNOWN_KEY),
    (_leg_doc(bid="1"), sf.UNKNOWN_KEY),
    ({k: v for k, v in _doc().items() if k != "preferences"}, sf.MISSING_KEY),
    (_doc(schema_version=2), sf.SCHEMA_VERSION_UNKNOWN),
    (_doc(schema_version="1"), sf.SCHEMA_VERSION_UNKNOWN),
    (_doc(schema_version=True), sf.SCHEMA_VERSION_UNKNOWN),
    (_leg_doc(contract_id=None), sf.MISSING_CONTRACT_ID),
    (_leg_doc(contract_id="101"), sf.MISSING_CONTRACT_ID),
    (_leg_doc(contract_id=0), sf.MISSING_CONTRACT_ID),
    (_leg_doc(quantity=True), sf.MALFORMED),
    (_leg_doc(expiry="13-10-2026"), sf.MALFORMED),
    (_leg_doc(action="SHORT"), sf.MALFORMED),
    (_doc(legs="x"), sf.MALFORMED),
    (_doc(risk_limits={"max_loss": 5000}), sf.NOT_DECIMAL_STRING),
    (_doc(underlying="BANKNIFTY"), sf.INVALID_DEFINITION),
])
def test_ac5_a_document_that_is_not_exactly_the_form_is_refused(doc, code):
    with pytest.raises(sf.StoredFormError) as err:
        sf.from_document(doc, _resolve())
    assert err.value.code == code


def test_ac5_a_missing_contract_id_key_is_refused_with_its_own_code():
    doc = _doc()
    del doc["legs"][2]["contract_id"]
    with pytest.raises(sf.StoredFormError) as err:
        sf.from_document(doc, _resolve())
    assert err.value.code == sf.MISSING_CONTRACT_ID


def test_ac5_a_contract_id_no_longer_in_the_catalogue_is_refused_never_replaced():
    """ADR-016: the catalogue lost id 104; even though 22200 PE exists under another id, nothing is substituted."""
    catalogue = {k: v for k, v in CATALOGUE.items() if k != 104} | {999: (Instrument.PE, Decimal("22200"))}
    with pytest.raises(sf.StoredFormError) as err:
        sf.loads(sf.dumps(_iron_condor()), _resolve(catalogue))
    assert err.value.code == sf.CONTRACT_NOT_IN_CATALOGUE and "104" in err.value.detail


def test_ac5_a_contract_whose_terms_changed_is_refused():
    catalogue = dict(CATALOGUE) | {101: (Instrument.CE, Decimal("22850"))}
    with pytest.raises(sf.StoredFormError) as err:
        sf.loads(sf.dumps(_iron_condor()), _resolve(catalogue))
    assert err.value.code == sf.CONTRACT_TERMS_CHANGED


def test_ac5_a_saved_draft_on_a_contract_that_has_since_expired_still_loads_exactly():
    saved = _iron_condor()
    assert sf.loads(sf.dumps(saved), _resolve(live=False)) == saved


@pytest.mark.parametrize("choices, resolve, code", [
    ([sf.LegChoice(105, Action.SELL, LOT)], _resolve(), sf.CONTRACT_NOT_IN_CATALOGUE),
    ([sf.LegChoice(101, Action.SELL, LOT)], _resolve(live=False), sf.CONTRACT_NOT_LIVE),
    ([sf.LegChoice(101, Action.SELL, 64)], _resolve(), sf.QUANTITY_NOT_LOT_MULTIPLE),
    ([sf.LegChoice(101, Action.SELL, LOT), sf.LegChoice(101, Action.BUY, LOT)], _resolve(), sf.INVALID_DEFINITION),
])
def test_ac5_save_draft_takes_terms_only_from_live_catalogue_contracts(choices, resolve, code):
    with pytest.raises(sf.StoredFormError) as err:
        sf.build_from_catalogue("NIFTY", choices, resolve)
    assert err.value.code == code


def test_ac5_save_draft_refuses_a_contract_of_another_underlying():
    with pytest.raises(sf.StoredFormError) as err:
        sf.build_from_catalogue("SENSEX", IRON_CONDOR, _resolve())
    assert err.value.code == sf.UNDERLYING_MISMATCH


def test_ac5_history_entry_round_trip_and_summary():
    old = _iron_condor()
    catalogue = dict(CATALOGUE) | {105: (Instrument.CE, Decimal("23100"))}
    new = sf.build_from_catalogue("NIFTY", [IRON_CONDOR[0], sf.LegChoice(105, Action.BUY, LOT), *IRON_CONDOR[2:]],
                                  _resolve(catalogue))
    summary = sf.change_summary(old, new)
    assert summary == "removed leg BUY 23000 CE 2026-10-13 x65; added leg BUY 23100 CE 2026-10-13 x65"
    at = datetime.datetime(2026, 10, 8, 10, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    entry = sf.HistoryEntry(1, at, summary, old)
    doc = json.loads(json.dumps(sf.entry_to_document(entry)), parse_float=lambda s: pytest.fail("float " + s))
    assert sf.entry_from_document(doc, _resolve(catalogue)) == entry
    doc["ltp"] = "1"
    with pytest.raises(sf.StoredFormError) as err:
        sf.entry_from_document(doc, _resolve(catalogue))
    assert err.value.code == sf.UNKNOWN_KEY
