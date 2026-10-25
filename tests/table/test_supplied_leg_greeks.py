"""REQ-050 AC-1 (W-136): the table takes the caller's per-unit Greeks of an option leg, else computes its own; it never
caches, never lets a futures leg or a leg without IV carry one, and rounds and scales exactly as before."""
from collections import Counter
from decimal import Decimal as D

import pytest
from table_fixtures import gated, nifty_input, nifty_leg

import ofo.table.model as table_model
from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action, Instrument
from ofo.engine.model import leg_greeks_unrounded
from ofo.table import build_table


@pytest.fixture
def counted(monkeypatch):
    calls: Counter = Counter()
    real = table_model.leg_greeks_unrounded

    def count(model, leg):
        calls[leg.contract] += 1
        return real(model, leg)

    monkeypatch.setattr(table_model, "leg_greeks_unrounded", count)
    return calls


def cells(table):
    return {(r.row_id, str(c)): (cell.value, cell.per_unit) for r in table.rows for c, cell in r.cells.items()
            if cell.per_unit is not None or str(c).endswith(("DELTA", "GAMMA", "THETA", "VEGA"))}


def test_ac1_supplied_greeks_are_used_and_the_table_computes_none(golden, counted):
    """AC-1: with a Greeks for every leg the engine is not called by the table and the cells equal the own-computed."""
    own = build_table(golden)
    assert sum(counted.values()) == 2 * len(golden.legs)  # a leg row and the TOTAL row each compute
    supplied = [leg_greeks_unrounded(golden, leg) for leg in golden.legs]
    counted.clear()
    given = build_table(golden, leg_greeks=supplied)
    assert sum(counted.values()) == 0
    assert cells(given) == cells(own)  # Decimal equality, rounding and scaling unchanged


def test_ac1_a_none_entry_is_computed_by_the_table(golden, counted):
    """AC-1: None means 'compute it here, as today'."""
    supplied = [None] + [leg_greeks_unrounded(golden, leg) for leg in golden.legs[1:]]
    counted.clear()
    table = build_table(golden, leg_greeks=supplied)
    assert counted == Counter({golden.legs[0].contract: 2})
    assert cells(table) == cells(build_table(golden))


def test_ac1_a_futures_leg_keeps_its_constant_greeks_and_a_supplied_value_for_it_is_refused(counted):
    """AC-1: a futures leg is untouched; a Greeks supplied for it (or for a leg without IV) is refused."""
    fut = nifty_leg(Action.BUY, Instrument.FUT, None, "23050.00", "23060.00")
    pe = nifty_leg(Action.SELL, Instrument.PE, "23000", "86.00", "80.00", "0.108838")
    no_iv = nifty_leg(Action.SELL, Instrument.CE, "23400", "91.50", "78.00")
    inputs = gated(nifty_input([fut, pe, no_iv]).inputs)
    pe_greeks = leg_greeks_unrounded(inputs, inputs.legs[1])
    counted.clear()
    table = build_table(inputs, leg_greeks=[None, pe_greeks, None])
    assert counted == Counter()  # the futures constant, the supplied PE, and no IV: nothing computed
    assert cells(table) == cells(build_table(inputs))
    for bad in ([pe_greeks, pe_greeks, None], [None, pe_greeks, pe_greeks]):
        with pytest.raises(ValueError, match="option leg that has an IV"):
            build_table(inputs, leg_greeks=bad)


def test_ac1_the_shape_of_the_supplied_list_is_an_allow_list(golden):
    """AC-1: one entry per leg, each a Greeks or None; anything else is refused."""
    good = [leg_greeks_unrounded(golden, leg) for leg in golden.legs]
    with pytest.raises(ValueError, match="one entry per leg"):
        build_table(golden, leg_greeks=good[:-1])
    for junk in (D("1"), (D("1"),) * 4, "greeks", 7):
        with pytest.raises(ValueError, match="option leg that has an IV"):
            build_table(golden, leg_greeks=[junk, *good[1:]])
    assert isinstance(good[0], Greeks)
