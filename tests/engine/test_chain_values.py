"""REQ-080 AC-2 (IV and delta from the engine), REQ-029 AC-3 / REQ-087 AC-1/AC-4/AC-5 (the extra chain values).

The Proof of row 19: ``chain_greeks`` on two real strikes each of the recorded NIFTY and SENSEX chains (the 2026-10-08
09:20:09 IST replay in ``tests/fixtures/kite_ws``), against numbers worked out independently with a separate
Black-Scholes (math.erf, bisection) at the same inputs: r = 0.065, q = 0 (the spot fallback forward, two strikes cannot
make a parity forward), T = seconds to 15:30 IST on the expiry / (365 x 86400).

NIFTY spot 22,533.25, expiry 2026-10-13, T = 0.014402302...:
  22500 CE LTP 151.30 -> IV 0.113440, delta  0.573009
  22550 PE LTP 145.10 -> IV 0.136520, delta -0.492031
SENSEX spot 72,443.48, expiry 2026-10-08, T = 0.000703672...:
  72500 CE LTP 144.35 -> IV 0.221176, delta  0.451372
  72400 PE LTP 206.05 -> IV 0.298389, delta -0.465898
The engine rounds IV and delta to 4 places, so each is compared within 0.00006 of the independent figure.
"""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal

import pytest
from ofo.engine.chain_values import CellValues, cell_values, chain_greeks, in_the_money
from ofo.engine.legs import Instrument
from ofo.engine.model import iv_price
from ofo.marketdata.quote import NormalizedQuote, SourceMetadata
from ofo.rules.inputs import DataHealth

D = Decimal
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = D("0.065")
TOLERANCE = D("0.00006")
SPOT = D("22976.85")
LOT = 65


def _quote(instrument_id: str, underlying: str, kind: Instrument | None, expiry: datetime.date | None,  # noqa: PLR0913
           strike: str | None, ltp: str, health: DataHealth = DataHealth.AVAILABLE) -> NormalizedQuote:
    segment = "NSE_FO" if kind is not None else "INDICES"
    return NormalizedQuote(instrument_id, underlying, "NSE", segment, kind, expiry,
                           None if strike is None else D(strike), D(ltp), *([None] * 10), VALUATION,
                           SourceMetadata("recorded", "kite-2026-10-08"), health)


def _greeks(underlying: str, spot: str, expiry: datetime.date, rows: list[tuple[str, Instrument, str, str]]):
    spot_quote = _quote("INDEX", underlying, None, None, None, spot)
    chain = [_quote(i, underlying, kind, expiry, strike, ltp) for i, kind, strike, ltp in rows]
    return chain_greeks(chain, spot_quote, expiry, VALUATION, RATE)


NIFTY_ROWS = [("NSE_FO:44612", Instrument.CE, "22500", "151.30"), ("NSE_FO:44615", Instrument.PE, "22550", "145.10")]
SENSEX_ROWS = [("BSE_FO:889331", Instrument.CE, "72500", "144.35"), ("BSE_FO:889261", Instrument.PE, "72400", "206.05")]


def test_core_nifty_two_real_strikes_iv_and_delta_match_the_independent_figures():
    """AC-2: the core. IV and delta of two recorded NIFTY strikes come from the engine and equal the hand figures."""
    out = _greeks("NIFTY", "22533.25", datetime.date(2026, 10, 13), NIFTY_ROWS)
    ce, pe = out["NSE_FO:44612"], out["NSE_FO:44615"]
    assert abs(ce.iv - D("0.113440")) <= TOLERANCE and abs(ce.delta - D("0.573009")) <= TOLERANCE
    assert abs(pe.iv - D("0.136520")) <= TOLERANCE and abs(pe.delta - D("-0.492031")) <= TOLERANCE


def test_sensex_two_real_strikes_iv_and_delta_match_the_independent_figures():
    """AC-2 (attack 6): SENSEX as well as NIFTY, with its own expiry day."""
    out = _greeks("SENSEX", "72443.48", datetime.date(2026, 10, 8), SENSEX_ROWS)
    ce, pe = out["BSE_FO:889331"], out["BSE_FO:889261"]
    assert abs(ce.iv - D("0.221176")) <= TOLERANCE and abs(ce.delta - D("0.451372")) <= TOLERANCE
    assert abs(pe.iv - D("0.298389")) <= TOLERANCE and abs(pe.delta - D("-0.465898")) <= TOLERANCE


def test_ac_2_a_contract_without_a_live_price_gets_no_greeks_not_a_guess():
    """AC-2/AC-5: a zero-priced contract is left out; the priced one still gets its values."""
    rows = [*NIFTY_ROWS, ("NSE_FO:44616", Instrument.CE, "22600", "0")]
    out = _greeks("NIFTY", "22533.25", datetime.date(2026, 10, 13), rows)
    assert "NSE_FO:44616" not in out and set(out) == {"NSE_FO:44612", "NSE_FO:44615"}


def test_ac_2_expired_expiry_gives_no_greeks():
    """AC-2: an expiry at or before the valuation is refused by the engine: an empty answer, never a raise."""
    assert _greeks("NIFTY", "22533.25", datetime.date(2026, 10, 7), NIFTY_ROWS) == {}


def test_greeks_without_a_spot_quote_are_empty_not_guessed():
    """AC-2: no index price, no Greeks."""
    assert chain_greeks([], None, datetime.date(2026, 10, 13), VALUATION, RATE) == {}


# ---- the extra chain values (REQ-087), kept with the file they belong to ---------------------------------------------
# NIFTY 22,900 CE, LTP 150.00, spot 22,976.85, lot 65: intrinsic 76.85, time value 73.15, breakeven 23050,
# breakeven % = 73.15 / 22976.85 x 100 = 0.3184 -> 0.32, per lot 9750.00. Put 23,100 PE LTP 80.00: intrinsic 123.15,
# time value -43.15, breakeven 23020, % = 43.15 / 22976.85 x 100 = 0.1878 -> 0.19.

def test_call_example_from_req_087_ac_4():
    """REQ-087 AC-4: the worked call example."""
    v = cell_values("CE", D("22900"), D("150.00"), SPOT, LOT)
    assert v == CellValues(per_lot=D("9750.00"), intrinsic=D("76.85"), time_value=D("73.15"), breakeven=D("23050.00"),
                           breakeven_pct=D("0.32"))


def test_put_negative_time_value_is_shown_not_clamped():
    """REQ-087 AC-4: a negative time value is shown as it is."""
    v = cell_values("PE", D("23100"), D("80.00"), SPOT, LOT)
    assert (v.intrinsic, v.time_value, v.breakeven, v.breakeven_pct, v.per_lot) == (
        D("123.15"), D("-43.15"), D("23020.00"), D("0.19"), D("5200.00"))


@pytest.mark.parametrize("ltp", [None, D("0"), D("0.00")])
def test_missing_or_zero_ltp_is_absent_never_zero(ltp):
    """REQ-087 AC-5: no price -> no price-dependent value, a real zero intrinsic stays 0."""
    v = cell_values("PE", D("22900"), ltp, SPOT, LOT)
    assert v.intrinsic == D("0.00")
    assert v.per_lot is None and v.time_value is None and v.breakeven is None and v.breakeven_pct is None


def test_sensex_lot_20_per_lot_and_a_future_is_not_an_option_side():
    """REQ-087 AC-4: SENSEX per-lot value; a future is refused."""
    assert cell_values("CE", D("80000"), D("12.50"), D("80010"), 20).per_lot == D("250.00")
    with pytest.raises(ValueError):
        cell_values("FUT", D("1"), D("1"), SPOT, LOT)


@pytest.mark.parametrize(("kind", "strike", "spot", "expected"), [
    ("CE", "22900", SPOT, True), ("CE", "23000", SPOT, False), ("PE", "23000", SPOT, True),
    ("PE", "22900", SPOT, False), ("CE", "22976.85", SPOT, False), ("PE", "22976.85", SPOT, False),
    ("CE", "22900", None, None), ("PE", "23000", None, None), ("CE", "22900", D("0"), None)])
def test_req_087_ac_2_in_the_money_sides(kind, strike, spot, expected):
    """REQ-087 AC-2: calls below the spot and puts above it; None without a live spot."""
    assert in_the_money(kind, D(strike), spot) is expected


# --- One IV price rule (ADR-172) for the picker and the outcome leg: chunk-2 Tier A review, area A ---------------
NEAR = datetime.date(2026, 10, 13)
ANCHOR = "NSE_FO:44614"  # one recorded NIFTY 13-Oct option: the snapshot then carries the whole 13-Oct chain


@pytest.fixture(scope="module")
def recorded():
    """The 2026-10-08 09:20:09 replay: the NIFTY 13-Oct chain with its parity forward and live bid/ask."""
    from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
    from ofo.outcome import read_snapshot
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider, read_snapshot(provider, "NIFTY", [ANCHOR], VALUATION, RATE)


def _outcome_leg_iv(provider, instrument_id):
    from ofo.engine.legs import Action
    from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, read_snapshot
    snap = read_snapshot(provider, "NIFTY", [instrument_id], VALUATION, RATE)
    plan = StrategyDefinition("NIFTY", (PlannedLeg(instrument_id, Action.BUY, 1, D("10"), VALUATION),))
    return build_outcome(plan, snap).legs[0].iv


def test_core_picker_iv_equals_outcome_leg_iv_on_the_recorded_frames(recorded):
    """The core: the leg picker's IV and the outcome leg's IV for one contract at one instant are one engine number,
    because both solve from the one ADR-172 price (mid when both sides are live and ask >= bid, else LTP). Before the
    fix the 22150 CE (deep in the money, stale LTP, live mid) showed 0.147669 in the picker vs 0.138008 on the leg."""
    provider, snap = recorded
    chain = snap.chains[NEAR]
    picker = chain_greeks(chain, snap.spot, NEAR, VALUATION, RATE)
    by_key = {(q.instrument_type, q.strike): q for q in chain}
    for kind, strike in ((Instrument.CE, "22150"), (Instrument.CE, "22550"), (Instrument.PE, "22550"),
                         (Instrument.PE, "22900"), (Instrument.CE, "23000")):
        q = by_key[(kind, D(strike))]
        leg_iv = _outcome_leg_iv(provider, q.instrument_id)
        assert leg_iv is not None and q.instrument_id in picker, (kind, strike)
        assert picker[q.instrument_id].iv == leg_iv, (kind, strike, picker[q.instrument_id].iv, leg_iv)
    ce = by_key[(Instrument.CE, D("22150"))]
    assert ce.bid and ce.ask and ce.ask >= ce.bid and ce.ltp != iv_price(ce)  # the mid branch, on real data


def _priced(ltp, bid, ask):
    q = _quote("NSE_FO:44612", "NIFTY", Instrument.CE, NEAR, "22500", "1")
    return dataclasses.replace(q, ltp=None if ltp is None else D(ltp), bid=None if bid is None else D(bid),
                               ask=None if ask is None else D(ask))


@pytest.mark.parametrize(("ltp", "bid", "ask", "expected"), [
    ("151.30", "150.00", "151.05", "150.52"),  # both sides live, ask >= bid: the mid (half-even to 0.01)
    ("151.30", "150.00", "150.00", "150.00"),  # a zero-width book is still a mid
    ("151.30", None, "151.05", "151.30"),      # no bid: LTP
    ("151.30", "150.00", None, "151.30"),      # no ask: LTP
    ("151.30", "0", "151.05", "151.30"),       # a bid of 0 is no live side: LTP
    ("151.30", "151.05", "150.00", "151.30"),  # ask < bid (crossed): LTP
    (None, None, None, None),                  # no LTP and no mid: no IV price
])
def test_iv_price_is_the_mid_when_both_sides_live_else_the_ltp(ltp, bid, ask, expected):
    """ADR-172 answer states: mid / one side missing / zero side / crossed / nothing."""
    assert iv_price(_priced(ltp, bid, ask)) == (None if expected is None else D(expected))


def test_picker_solves_from_the_mid_and_a_crossed_book_from_the_ltp():
    """The picker itself (not only the helper) takes the ADR-172 price: a live book moves the IV off the LTP figure;
    a crossed book leaves it on the LTP figure."""
    spot = _quote("INDEX", "NIFTY", None, None, None, "22533.25")

    def iv(q):
        return chain_greeks([q], spot, NEAR, VALUATION, RATE)["NSE_FO:44612"].iv
    on_ltp = iv(_priced("151.30", None, None))
    assert iv(_priced("151.30", "151.05", "150.00")) == on_ltp
    on_mid = iv(_priced("151.30", "140.00", "141.00"))
    assert on_mid < on_ltp
