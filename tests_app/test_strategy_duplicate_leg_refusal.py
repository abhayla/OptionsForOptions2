"""27 Nov 2026 (live screen test, item 4): a draft with two legs on the same contract is refused with its OWN sentence,
naming the legs and the contract the way the screens print it (display_contract, "1 Dec", never ISO), not the generic
"cannot be saved as sent". Wording is pending owner read."""
import datetime
from decimal import Decimal

import pytest

from ofo.engine.legs import Action, Instrument
from ofo.strategy import stored_form as sf
from ofo_app.routes.strategies import refused_answer

EXPIRY = datetime.date(2025, 12, 1)
LOT = 75
GENERIC = "This strategy definition cannot be saved as sent."


def _resolve(contract_id):
    strikes = {1: Decimal("25900"), 2: Decimal("25900"), 3: Decimal("26000")}  # ids 1 and 2: the same terms
    return sf.CatalogueTerms("NIFTY", Instrument.CE, strikes[contract_id], EXPIRY, LOT, True)


def _refusal(*choices):
    with pytest.raises(sf.StoredFormError) as err:
        sf.build_from_catalogue("NIFTY", list(choices), _resolve)
    return refused_answer(err.value, 422)


def test_same_contract_same_side_names_legs_contract_and_side():
    out = _refusal(sf.LegChoice(1, Action.SELL, LOT), sf.LegChoice(3, Action.BUY, LOT), sf.LegChoice(2, Action.SELL, LOT))
    m = out.message
    assert m.what_happened == "Legs 1 and 3 are the same contract and side (NIFTY 1 Dec 25900 CE, Sell)."
    assert "Join them into one leg with more lots, or change one of them." in m.next_action
    assert m.what_happened != GENERIC and "2025-12-01" not in m.what_happened


def test_same_catalogue_id_twice():
    m = _refusal(sf.LegChoice(1, Action.BUY, LOT), sf.LegChoice(1, Action.BUY, LOT)).message
    assert m.what_happened == "Legs 1 and 2 are the same contract and side (NIFTY 1 Dec 25900 CE, Buy)."


def test_same_contract_opposite_sides_is_said_truthfully():
    m = _refusal(sf.LegChoice(1, Action.SELL, LOT), sf.LegChoice(2, Action.BUY, LOT)).message
    assert m.what_happened == "Legs 1 and 2 are the same contract (NIFTY 1 Dec 25900 CE), one Sell and one Buy."
    assert "same contract and side" not in m.what_happened


def test_other_invalid_definitions_still_get_the_generic_sentence():
    with pytest.raises(sf.StoredFormError) as err:
        sf.build_from_catalogue("NIFTY", [], _resolve)  # no legs
    assert refused_answer(err.value, 422).message.what_happened == GENERIC
