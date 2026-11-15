"""ADR-300: the REAL ``_sold_deltas`` (the route tests stub it): absolute values, sold OPTION legs only, the lot count
does not scale the per-unit delta, Decimal type. The engine call is replaced by a fixed per-strike table."""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from types import SimpleNamespace

from ofo.engine.legs import Action, Instrument
from ofo.outcome import service

EXPIRY = datetime.date(2026, 10, 13)
DELTAS = {D("24000"): D("-0.4600000000000012"), D("25000"): D("0.1812345678901234"), D("24500"): D("0.5")}


def _leg(action, instrument, strike, quantity, iv="0.2"):
    return SimpleNamespace(action=action, instrument=instrument, strike=D(strike), expiry=EXPIRY, quantity=quantity,
                           iv=None if iv is None else D(iv))


def _model(*legs):
    return SimpleNamespace(legs=legs, expiry_model=lambda _expiry: object())


def _g(delta):
    return None if delta is None else SimpleNamespace(delta=D(delta))


def test_the_real_sold_deltas_are_absolute_sold_options_only_and_not_scaled_by_lots() -> None:
    model = _model(_leg(Action.SELL, Instrument.PE, "24000", 130),  # a sold put: engine delta negative, two lots
                   _leg(Action.SELL, Instrument.CE, "25000", 65),  # a sold call, one lot
                   _leg(Action.BUY, Instrument.CE, "24500", 65),  # a bought leg: not read
                   _leg(Action.SELL, Instrument.FUT, "24500", 65))  # a future: not an option
    greeks = [_g("-0.4600000000000012"), _g("0.1812345678901234"), _g("0.5"), None]  # the table's shared per-leg Greeks
    got = service._sold_deltas(model, greeks)
    assert got == (("PE", D("0.4600000000000012")), ("CE", D("0.1812345678901234")))
    assert all(isinstance(d, D) and d >= 0 for _, d in got)
    one_lot = service._sold_deltas(_model(_leg(Action.SELL, Instrument.PE, "24000", 65)), [_g("-0.4600000000000012")])
    assert one_lot == (("PE", D("0.4600000000000012")),)  # 65 or 130 units: the same per-unit delta


def test_a_sold_leg_with_no_iv_or_no_shared_scope_has_no_delta_and_is_still_listed() -> None:
    no_iv = _model(_leg(Action.SELL, Instrument.CE, "25000", 65, iv=None))
    assert service._sold_deltas(no_iv, [None]) == (("CE", None),)
    assert service._sold_deltas(no_iv, None) == (("CE", None),)  # no feed owner: nothing computed here
