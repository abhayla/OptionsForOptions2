"""Row 33 (REQ-029 AC-2 IV for every user, AC-3 Details Greeks; ADR-056/061/063/172): the Option Chain's per-cell IV and
Greeks come from the ONE engine, with the forward's basis said, and a missing input is absent (a dash), never 0.

Proof (step 1 hand check, a REAL recorded cell): the 2026-10-08 09:20:09 IST NIFTY replay
(``tests/fixtures/kite_ws/frames-2026-10-08-092000-10s.bin.gz``): spot 22,533.25, expiry 2026-10-13, 22500 CE LTP
151.30 and 22550 PE LTP 145.10, no bid/ask in the cell (so the ADR-172 IV price is the LTP). Worked out by hand with a
separate Black-Scholes (math.erf, 200-step bisection; scratch script, not the engine) at r = 0.065, q = 0 (two strikes
cannot make a parity forward: ADR-061's spot fallback), T = seconds from 09:20:09 IST to 15:30 IST on 2026-10-13 /
(365 x 86400) = 0.0144023021...:

  d1 = (ln(S/K) + (r + v^2/2) T) / (v sqrt T),  d2 = d1 - v sqrt T
  22500 CE: IV 0.113440, delta  0.573009, gamma 0.001279, theta -13.717193 / day, vega 10.607058 / vol point
  22550 PE: IV 0.136520, delta -0.492031, gamma 0.001080, theta -12.005448 / day, vega 10.786069 / vol point

The engine rounds every figure to 4 places, so IV and delta are compared within 0.00006, theta and vega within 0.0006
(a 4-place theta of -13.7172 sits 0.000007 from the hand figure; the slack covers the day-count rounding only).
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine.chain_values import ChainModel, chain_greeks, chain_model
from ofo.engine.legs import Instrument
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

D = Decimal
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
EXPIRY = datetime.date(2026, 10, 13)
RATE = D("0.065")
SPOT = "22533.25"
TIGHT = D("0.00006")
LOOSE = D("0.0006")
CE_ID, PE_ID = "NSE_FO:44612", "NSE_FO:44615"


def _quote(instrument_id: str, kind: Instrument | None, strike: str | None, ltp: str | None,  # noqa: PLR0913
           bid: str | None = None, ask: str | None = None,
           health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    segment = "NSE_FO" if kind is not None else "INDICES"
    return NormalizedQuote(instrument_id, "NIFTY", "NSE", segment, kind, None if kind is None else EXPIRY,
                           None if strike is None else D(strike), None if ltp is None else D(ltp),
                           None if bid is None else D(bid), None if ask is None else D(ask), *([None] * 8),
                           VALUATION, SourceMetadata("recorded", "kite-2026-10-08"), health)


def _spot(price: str | None = SPOT, health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    return _quote("NSE_INDEX:256265", None, None, price, health=health)


REAL = [_quote(CE_ID, Instrument.CE, "22500", "151.30"), _quote(PE_ID, Instrument.PE, "22550", "145.10")]


def _model(chain=REAL, spot=_spot(), valuation=VALUATION) -> ChainModel:  # noqa: B008 - fixed test inputs
    return chain_model(chain, spot, EXPIRY, valuation, RATE)


def test_proof_real_nifty_cell_iv_and_every_greek_equal_the_hand_check():
    """Step 1 (the Proof): the real recorded cells' IV and all four Greeks equal the independent hand figures, and the
    answer says its forward is the spot fallback (two strikes): never silent (ADR-061)."""
    model = _model()
    ce, pe = model.greeks[CE_ID], model.greeks[PE_ID]
    assert abs(ce.iv - D("0.113440")) <= TIGHT and abs(ce.delta - D("0.573009")) <= TIGHT
    assert abs(ce.gamma - D("0.001279")) <= TIGHT
    assert abs(ce.theta - D("-13.717193")) <= LOOSE and abs(ce.vega - D("10.607058")) <= LOOSE
    assert abs(pe.iv - D("0.136520")) <= TIGHT and abs(pe.delta - D("-0.492031")) <= TIGHT
    assert abs(pe.gamma - D("0.001080")) <= TIGHT
    assert abs(pe.theta - D("-12.005448")) <= LOOSE and abs(pe.vega - D("10.786069")) <= LOOSE
    assert (model.basis, model.missing) == ("SPOT_FALLBACK", None)
    assert chain_greeks(REAL, _spot(), EXPIRY, VALUATION, RATE) == model.greeks  # one calculator, two readers


@pytest.mark.parametrize(("state", "cell"), [
    ("live with no LTP", _quote("NSE_FO:44616", Instrument.CE, "22600", None)),
    ("LTP 0 (no price, F-29)", _quote("NSE_FO:44616", Instrument.CE, "22600", "0")),
    ("deep ITM stale price below intrinsic: engine refuses", _quote("NSE_FO:44616", Instrument.CE, "22000", "400.00")),
])
def test_attack_1_no_price_or_a_refusing_engine_gives_no_value_never_0(state, cell):
    """Attack 1: the bad cell is ABSENT (the screen draws a dash), never 0; the real cells keep their own numbers."""
    model = _model([*REAL, cell])
    assert cell.instrument_id not in model.greeks, state
    assert set(model.greeks) == {CE_ID, PE_ID}


def test_attack_1_a_cell_that_loses_its_price_never_keeps_the_previous_number():
    """Attack 1: each answer uses its own quotes: the CE priced, then not priced -> absent the second time."""
    assert CE_ID in _model().greeks
    later = _model([_quote(CE_ID, Instrument.CE, "22500", None), REAL[1]])
    assert CE_ID not in later.greeks and PE_ID in later.greeks


@pytest.mark.parametrize(("spot", "missing"), [
    (None, "SPOT_REFUSED"),
    (_spot(None), "SPOT_REFUSED"),
    (_spot(health=DataHealth.UNAVAILABLE), "SPOT_REFUSED"),
])
def test_attack_2_no_spot_gives_no_greeks_and_says_why(spot, missing):
    """Attack 2: spot missing -> every value absent, the reason named, no basis claimed."""
    model = _model(spot=spot)
    assert (dict(model.greeks), model.basis, model.missing) == ({}, None, missing)


def test_attack_2_a_forward_that_cannot_be_derived_gives_dashes_and_says_so():
    """Attack 2: the valuation at/after the expiry close -> the forward is refused: no Greek, FORWARD_UNAVAILABLE, no
    silent fall back to the spot (basis None)."""
    after_close = datetime.datetime(2026, 10, 13, 15, 30, tzinfo=IST)
    model = _model(valuation=after_close)
    assert (dict(model.greeks), model.basis, model.missing) == ({}, None, "FORWARD_UNAVAILABLE")


def test_attack_2_three_strikes_with_both_sides_quoted_use_the_parity_forward():
    """Attack 2 / ADR-061: 3 strikes with CE and PE bid/ask make a parity forward: the basis says PARITY."""
    rows = []
    for i, strike in enumerate(("22500", "22550", "22600")):
        c, p = D("151.30") - 25 * i, D("118.20") + 25 * i
        rows += [_quote(f"NSE_FO:5{i}0", Instrument.CE, strike, str(c), str(c - 1), str(c + 1)),
                 _quote(f"NSE_FO:5{i}1", Instrument.PE, strike, str(p), str(p - 1), str(p + 1))]
    model = _model(rows)
    assert (model.basis, model.missing) == ("PARITY", None)
    assert set(model.greeks) == {q.instrument_id for q in rows}
