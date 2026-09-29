"""REQ-071 AC-1 (W-049): calculators for the reference-video values, computed by the one engine.

Fixture: the scenario-calculations section 6 golden Iron Condor exactly as tests/engine/conftest.py holds it
(NIFTY 2026-10-27 expiry, 75 units per leg, valued 2026-10-17 15:30 IST = 10 calendar days before the close, spot
23200, rate 0.065; entry 42.50 / 86.00 / 91.50 / 44.00, LTP 38.20 / 72.50 / 78.00 / 39.50, IVs implied from those
LTPs). Net entry credit 86 + 91.50 - 42.50 - 44 = 91 per unit; wings 200 points. Rows 16 and 17 use the real
Zerodha instrument slice (tests/fixtures/instruments, captured 2026-09-29).

Every expected value below is computed by hand in its test's docstring, never pasted from this code's output.
"""
from __future__ import annotations

import dataclasses
import datetime
import time
from decimal import Decimal as D
from pathlib import Path

import pytest

from ofo.adjustment import metrics as m
from ofo.adjustment.registry import FeasibilityError, MetricRegistry
from ofo.engine import black_scholes as bs
from ofo.engine import legs as engine_legs
from ofo.engine import strategy as engine_strategy
from ofo.engine.black_scholes import IST
from ofo.engine.booked import MAX_CLOSED_LEGS, ClosedLeg, booked_pnl, remaining_profit
from ofo.engine.inputs import LegInput, StrategyInput
from ofo.engine.interfaces import MarginRequirement
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import UNLIMITED
from ofo.engine.strategy import Strategy
from ofo.instruments.catalogue import Catalogue
from ofo.instruments.parser import parse_instruments_csv
from ofo.strategy.definition import StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord

EXPIRY = datetime.date(2026, 10, 27)
VALUATION = datetime.datetime(2026, 10, 17, 15, 30, tzinfo=IST)
SPOT = D("23200")
RATE = D("0.065")
IRON_CONDOR = [
    (Action.BUY, Instrument.PE, "22800", "42.50", "38.20", "0.117446"),
    (Action.SELL, Instrument.PE, "23000", "86.00", "72.50", "0.108838"),
    (Action.SELL, Instrument.CE, "23400", "91.50", "78.00", "0.093349"),
    (Action.BUY, Instrument.CE, "23600", "44.00", "39.50", "0.102360"),
]
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"
MARGIN = MarginRequirement(total=D("100000.00"), source="test: stated as the broker's basket margin")


def leg_input(action, instrument, strike, entry, ltp=None, iv=None, expiry=EXPIRY, quantity=75) -> LegInput:
    return LegInput(underlying="NIFTY", contract=f"NIFTY{expiry:%y%b}{strike}{instrument.value}".upper(),
                    action=action, instrument=instrument, strike=None if strike is None else D(strike),
                    expiry=expiry, quantity=quantity, premium=D(entry), ltp=None if ltp is None else D(ltp),
                    iv=None if iv is None else D(iv))


def strategy_input(rows=IRON_CONDOR, margin=None, valuation=VALUATION, spot=SPOT) -> StrategyInput:
    return StrategyInput(underlying="NIFTY", underlying_level=spot, valuation_time=valuation, rate=RATE,
                         legs=tuple(leg_input(*row) for row in rows), margin=margin)


def closed(row, exit_price: str, ref: str) -> ClosedLeg:
    return ClosedLeg(leg_input(*row).leg, D(exit_price), ref)


@pytest.fixture
def golden() -> StrategyInput:
    return strategy_input()


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    cat = Catalogue()
    cat.load(parse_instruments_csv(FIXTURE))
    return cat


# --- Core ------------------------------------------------------------------------------------------------------
def test_core_golden_iron_condor_video_values_from_the_one_engine(golden):
    """AC-1 (core): rows 10, 28, 4 and 26 on the golden Iron Condor, one leg closed.

    Row 10, BUY 23600 CE closed at its LTP 39.50: booked (39.50 - 44.00) x 75 = -337.50. Open legs BUY 22800 PE,
    SELL 23000 PE, SELL 23400 CE: open credit 86 + 91.50 - 42.50 = 135/unit; between 23000 and 23400 every option
    expires worthless -> 135 x 75 = 10,125 (at 22800: 135 - 200 = -65 -> -4,875; above 23400 the short call only
    loses). Max profit 10,125; remaining = 10,125 - 337.50 = 9,787.50. With nothing closed, the whole condor's max
    profit is 91 x 75 = 6,825.

    Row 28, LTPs after a rally 5.00 / 10.00 / 250.00 / 140.00: (5 - 42.50) x 75 = -2,812.50; (86 - 10) x 75 =
    5,700; (91.50 - 250) x 75 = -11,887.50; (140 - 44) x 75 = 7,200; total -1,800. Margin blocked 1,00,000:
    1,800 / 1,00,000 x 100 = 1.80 %. At the fixture LTPs the strategy is +1,365 (not a loss) -> 0.00 %.

    Rows 4 and 26, independent calculator (Python math only, not this code): T = 10/365, sqrt(T) = 0.165521,
    SELL 23400 CE at IV 0.093349: ln(23200/23400) = -0.008584, (0.065 + 0.093349^2/2) T = 0.0019002, vol sqrt(T) =
    0.015451, d1 = (-0.008584 + 0.0019002)/0.015451 = -0.432558, N(d1) = 0.332668 -> delta 0.3327; model price at
    that IV 77.9995 -> 78.00 = its LTP, so 0.093349 is the IV implied from the LTP. Same for the other legs: d1 =
    0.995973 / 0.588463 / -0.895373 -> deltas -0.1596 / -0.2781 / 0.1853, prices 38.2004 / 72.4998 / 39.4997.
    """
    open_legs = strategy_input(IRON_CONDOR[:3])
    value = m.remaining_profit(open_legs, [closed(IRON_CONDOR[3], "39.50", "fill-1")])
    assert value.metric_id == 10 and value.value == D("9787.50")
    assert value.inputs["exits"] == (("fill-1", D("39.50")),)
    assert m.remaining_profit(golden, []).value == D("6825.00")

    rally = [row[:4] + (ltp, None) for row, ltp in zip(IRON_CONDOR, ["5.00", "10.00", "250.00", "140.00"])]
    loss = m.loss_percent_of_margin(strategy_input(rally, margin=MARGIN))
    assert loss.metric_id == 28 and loss.value == D("1.80")
    assert loss.inputs["unrealised_pnl"] == D("-1800.00") and loss.inputs["margin"] == D("100000.00")
    assert m.loss_percent_of_margin(strategy_input(margin=MARGIN)).value == D("0.00")

    deltas = [m.option_delta(golden, i).value for i in range(4)]
    assert deltas == [D("-0.1596"), D("-0.2781"), D("0.3327"), D("0.1853")]
    ivs = [m.implied_volatility(golden, i).value for i in range(4)]
    assert ivs == [D("0.117446"), D("0.108838"), D("0.093349"), D("0.102360")]
    delta_call = m.option_delta(golden, 2)
    assert delta_call.inputs["iv"] == D("0.093349") and delta_call.inputs["ltp"] == D("78.00")
    assert delta_call.inputs["rate"] == RATE and delta_call.inputs["spot"] == SPOT
    assert delta_call.inputs["years"] == D(10) / D(365) and delta_call.as_of == VALUATION


# --- Registry ---------------------------------------------------------------------------------------------------
def test_registry_holds_a_calculator_for_every_listed_pass_row_and_no_other():
    """AC-1: rows 4-11, 14, 16-18, 26-29 get calculators (all ``pass`` in the spec table); 12 and 13 (unclear),
    19-25 and 30 (unknown / fail / out of V1) do not, and the registry refuses one for row 13."""
    registry = m.build_registry()
    assert registry.registered_ids() == [4, 5, 6, 7, 8, 9, 10, 11, 14, 16, 17, 18, 26, 27, 28, 29]
    for metric_id in registry.registered_ids():
        assert registry.get(metric_id).feasibility == "pass"
        assert registry.calculator(metric_id) is m.CALCULATORS[metric_id]
    with pytest.raises(FeasibilityError):
        registry.register_calculator(13, m.pnl_at_level)
    fresh = MetricRegistry()
    with pytest.raises(FeasibilityError):
        fresh.register_calculator(12, m.pnl_at_level)


# --- Rows 5, 6, 7 -----------------------------------------------------------------------------------------------
def test_strike_distances_and_gap(golden):
    """AC-1 rows 5-7: SELL 23400 CE vs spot 23200: +200 points, 200/23200 x 100 = 0.862... -> 0.86 %. BUY 22800 PE:
    -400 points, -400/23200 x 100 = -1.724... -> -1.72 %. Gap 23400 CE / 23600 CE = 200; 22800 PE / 23400 CE = 600."""
    assert m.strike_distance_points(golden, 2).value == D("200")
    assert m.strike_distance_percent(golden, 2).value == D("0.86")
    assert m.strike_distance_points(golden, 0).value == D("-400")
    assert m.strike_distance_percent(golden, 0).value == D("-1.72")
    assert m.strike_gap(golden, 2, 3).value == D("200") and m.strike_gap(golden, 0, 2).value == D("600")
    assert m.strike_distance_points(golden, 2).inputs == {"spot": SPOT, "contract": golden.legs[2].contract,
                                                         "strike": D("23400")}


def test_leg_selection_is_refused_when_invalid(golden):
    """AC-1: a bool, negative or out-of-range leg index, a futures leg where a strike is needed, the same leg twice
    for a gap, and anything that is not a StrategyInput are refused."""
    for bad in (True, -1, 4, "0"):
        with pytest.raises(ValueError, match="leg index"):
            m.strike_distance_points(golden, bad)
    with pytest.raises(ValueError, match="two different legs"):
        m.strike_gap(golden, 1, 1)
    fut = strategy_input([(Action.BUY, Instrument.FUT, None, "23250.00", "23240.00", None)])
    with pytest.raises(ValueError, match="future"):
        m.strike_distance_points(fut, 0)
    with pytest.raises(ValueError, match="StrategyInput"):
        m.unrealised_pnl(golden.strategy)


# --- Rows 8, 11, 14 ---------------------------------------------------------------------------------------------
def test_unrealised_pnl_payoff_at_level_and_net_premium(golden):
    """AC-1 rows 8, 11, 14. Row 8: (38.20-42.50) x 75 = -322.50; (86-72.50) x 75 = 1,012.50; (91.50-78) x 75 =
    1,012.50; (39.50-44) x 75 = -337.50 -> 1,365.00. Row 11 at 22000 (below both puts): 91 - 200 = -109 x 75 =
    -8,175; at 23200 all expire worthless: 91 x 75 = 6,825. Row 14 at LTP: 72.50 + 78 - 38.20 - 39.50 = 72.80 x 75
    = 5,460.00."""
    assert m.unrealised_pnl(golden).value == D("1365.00")
    assert m.pnl_at_level(golden, D("22000")).value == D("-8175.00")
    assert m.pnl_at_level(golden, D("23200")).value == D("6825.00")
    assert m.net_premium_now(golden).value == D("5460.00")
    assert m.net_premium_now(golden).inputs["ltps"][golden.legs[2].contract] == D("78.00")
    with pytest.raises(ValueError, match="2 decimal places"):
        m.pnl_at_level(golden, D(23000.1))


# --- Rows 9, 10 -------------------------------------------------------------------------------------------------
def test_booked_pnl_of_closed_legs_and_running_total():
    """AC-1 row 9: BUY 23600 CE exited at 39.50: (39.50 - 44) x 75 = -337.50; SELL 23400 CE exited at 180.00:
    (91.50 - 180) x 75 = -6,637.50; running total -6,975.00. Nothing closed books 0."""
    result = m.booked_pnl([closed(IRON_CONDOR[3], "39.50", "f1"), closed(IRON_CONDOR[2], "180.00", "f2")], VALUATION)
    assert result.metric_id == 9
    assert result.value.per_leg == (D("-337.50"), D("-6637.50")) and result.value.total == D("-6975.00")
    assert booked_pnl([]).total == D(0)


def test_booked_pnl_refuses_duplicates_bad_items_and_absurd_sizes():
    """AC-1 row 9: the same exit fill twice, a non-ClosedLeg item, more than MAX_CLOSED_LEGS items, a float-built
    exit price, a missing reference, a non-Leg and a naive as_of are all refused."""
    one = closed(IRON_CONDOR[3], "39.50", "f1")
    with pytest.raises(ValueError, match="twice"):
        booked_pnl([one, one])
    with pytest.raises(ValueError, match="ClosedLeg"):
        booked_pnl([one.leg])
    with pytest.raises(ValueError, match="limit"):
        booked_pnl([closed(IRON_CONDOR[3], "39.50", f"f{i}") for i in range(MAX_CLOSED_LEGS + 1)])
    with pytest.raises(ValueError, match="2 decimal places"):
        ClosedLeg(one.leg, D(39.3), "f9")
    with pytest.raises(ValueError, match="reference"):
        ClosedLeg(one.leg, D("39.50"), " ")
    with pytest.raises(ValueError, match="needs a Leg"):
        ClosedLeg("NIFTY 23600 CE", D("39.50"), "f9")
    with pytest.raises(ValueError, match="timezone-aware"):
        m.booked_pnl([one], datetime.datetime(2026, 10, 17, 15, 30))
    start = time.perf_counter()
    booked_pnl([closed(IRON_CONDOR[3], "39.50", f"f{i}") for i in range(MAX_CLOSED_LEGS)])
    assert time.perf_counter() - start < 1.0


def test_remaining_profit_unlimited_and_booked_profit_cases():
    """AC-1 row 10: open legs BUY 22800 PE, SELL 23000 PE, BUY 23600 CE have an unbounded upside (long call, no
    short call above it) -> UNLIMITED. A net booked PROFIT (SELL 23400 CE closed at 78.00: (91.50-78) x 75 =
    +1,012.50) is outside the owner's reading (Q246 names booked losses) and is refused, not guessed."""
    open_legs = strategy_input([IRON_CONDOR[0], IRON_CONDOR[1], IRON_CONDOR[3]])
    assert m.remaining_profit(open_legs, [closed(IRON_CONDOR[2], "180.00", "f2")]).value is UNLIMITED
    with pytest.raises(ValueError, match="net profit"):
        m.remaining_profit(open_legs, [closed(IRON_CONDOR[2], "78.00", "f2")])
    with pytest.raises(ValueError, match="Strategy"):
        remaining_profit(open_legs, [])


# --- Rows 16, 17 (real instrument catalogue) -------------------------------------------------------------------
REAL_EXPIRY = datetime.date(2026, 10, 6)
REAL_VALUATION = datetime.datetime(2026, 9, 29, 15, 30, tzinfo=IST)


def real_input(quantity: int, expiry=REAL_EXPIRY) -> StrategyInput:
    return StrategyInput(underlying="NIFTY", underlying_level=D("23200"), valuation_time=REAL_VALUATION, rate=RATE,
                         legs=(leg_input(Action.SELL, Instrument.CE, "23400", "91.50", expiry=expiry,
                                         quantity=quantity),))


def test_lots_from_the_real_instrument_catalogue(catalogue):
    """AC-1 row 16: the real Zerodha slice lists NIFTY 2026-10-06 options with lot size 65 (fixture row
    ``NIFTY26O0623150CE ... 65,CE``): 130 units = 130 / 65 = 2 lots. 75 units is not a whole number of 65-unit lots
    and is refused; so is a catalogue that is not a Catalogue."""
    value = m.lots(real_input(130), 0, catalogue)
    assert value.value == {"units": 130, "lot_size": 65, "lots": 2}
    with pytest.raises(ValueError, match="whole number of lots"):
        m.lots(real_input(75), 0, catalogue)
    with pytest.raises(ValueError, match="Catalogue"):
        m.lots(real_input(130), 0, {"lot_size": 65})


def test_days_to_expiry_calendar_and_trading(catalogue):
    """AC-1 row 17: 2026-09-29 (Tue) to 2026-10-06 (Tue) = 7 calendar days. Weekdays after the 29th up to the 6th:
    Sep 30, Oct 1, Oct 2, Oct 5, Oct 6 = 5; with 2 Oct given as a holiday (an input here; 2 October is NSE's fixed
    Gandhi Jayanti holiday, the 2026 list itself was not fetched) = 4. A weekend holiday changes nothing."""
    value = m.days_to_expiry(real_input(130), 0, catalogue, frozenset({datetime.date(2026, 10, 2)}))
    assert value.value == {"calendar_days": 7, "trading_days": 4}
    assert m.days_to_expiry(real_input(130), 0, catalogue, frozenset()).value["trading_days"] == 5
    weekend = frozenset({datetime.date(2026, 10, 3)})
    assert m.days_to_expiry(real_input(130), 0, catalogue, weekend).value["trading_days"] == 5


def test_days_to_expiry_refuses_bad_inputs(catalogue):
    """AC-1 row 17: an expiry the catalogue does not list (NIFTY 2026-10-13), a valuation after expiry, holidays
    that are not a frozenset of dates (a list, a datetime, too many), and a non-Catalogue are refused."""
    with pytest.raises(ValueError, match="lists no NIFTY contract"):
        m.days_to_expiry(real_input(130, expiry=datetime.date(2026, 10, 13)), 0, catalogue, frozenset())
    late = dataclasses.replace(real_input(130), valuation_time=datetime.datetime(2026, 10, 7, 9, 0, tzinfo=IST))
    with pytest.raises(ValueError, match="after the"):
        m.days_to_expiry(late, 0, catalogue, frozenset())
    with pytest.raises(ValueError, match="frozenset"):
        m.days_to_expiry(real_input(130), 0, catalogue, [datetime.date(2026, 10, 2)])
    with pytest.raises(ValueError, match="datetime.date"):
        m.days_to_expiry(real_input(130), 0, catalogue, frozenset({datetime.datetime(2026, 10, 2, tzinfo=IST)}))
    many = frozenset(datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(m.MAX_HOLIDAYS + 1))
    with pytest.raises(ValueError, match="at most"):
        m.days_to_expiry(real_input(130), 0, catalogue, many)
    with pytest.raises(ValueError, match="Catalogue"):
        m.days_to_expiry(real_input(130), 0, None, frozenset())


# --- Row 18 -----------------------------------------------------------------------------------------------------
def test_market_clock_reads_exchange_time():
    """AC-1 row 18: 10:00 UTC is 10:00 + 5:30 = 15:30 IST. A naive clock is refused."""
    value = m.market_clock(datetime.datetime(2026, 9, 29, 10, 0, tzinfo=datetime.timezone.utc))
    assert value.value == datetime.time(15, 30, tzinfo=IST)
    with pytest.raises(ValueError, match="timezone-aware"):
        m.market_clock(datetime.datetime(2026, 9, 29, 10, 0))


# --- Rows 27, 28 ------------------------------------------------------------------------------------------------
def test_margin_is_the_brokers_stated_value(golden):
    """AC-1 row 27: required = the stated 1,00,000.00, available = the broker-stated 2,50,000.00, both returned as
    given with the source recorded. No stated margin, or a float-built available margin, is refused."""
    value = m.margin(strategy_input(margin=MARGIN), D("250000.00"))
    assert value.value == {"required": D("100000.00"), "available": D("250000.00")}
    assert value.inputs["source"] == MARGIN.source
    with pytest.raises(ValueError, match="Zerodha's margin API"):
        m.margin(golden, D("250000.00"))
    with pytest.raises(ValueError, match="2 decimal places"):
        m.margin(strategy_input(margin=MARGIN), D(0.1))


def test_loss_percent_refuses_missing_or_zero_margin(golden):
    """AC-1 row 28, near the video's own example ("loss is Rs. 19,000 at Rs. 5,00,000 ... almost 4%"): one SELL
    23400 CE, 75 units, entry 91.50, LTP 344.83: (91.50 - 344.83) x 75 = -18,999.75; 18,999.75 / 5,00,000 x 100 =
    3.79995 -> 3.80 (half-even to 0.01). No stated margin, and a stated margin of 0, are refused."""
    one = strategy_input([(Action.SELL, Instrument.CE, "23400", "91.50", "344.83", None)],
                         margin=MarginRequirement(D("500000.00"), "test"))
    assert m.loss_percent_of_margin(one).value == D("3.80")
    with pytest.raises(ValueError, match="Zerodha's margin API"):
        m.loss_percent_of_margin(golden)
    with pytest.raises(ValueError, match="is 0"):
        m.loss_percent_of_margin(strategy_input(margin=MarginRequirement(D("0"), "test")))


# --- Row 29 -----------------------------------------------------------------------------------------------------
def _definition(quantity: int) -> StrategyDefinition:
    legs = tuple(dataclasses.replace(leg_input(*row).leg, quantity=quantity) for row in IRON_CONDOR)
    return StrategyDefinition.from_engine("NIFTY", Strategy(legs), risk_limits={"max_loss": D("8175")})


def _broker(units: int) -> Position:
    signs = [1, -1, -1, 1]
    return Position(tuple((("NIFTY", row[1], D(row[2]), EXPIRY), units * s) for row, s in zip(IRON_CONDOR, signs)))


def test_adjustments_made_counts_activated_versions_after_the_entry():
    """AC-1 row 29: v1 activated = the entry, 0 adjustments; v2 (2 lots) activated = 1; v3 (3 lots) rejected
    still 1; v4 (3 lots) activated = 2. The count is read from the record's own outcomes."""
    t0 = datetime.datetime(2026, 10, 1, 9, 20, tzinfo=IST)
    rec = StrategyRecord(_definition(75), at=t0, clock=lambda: t0 + datetime.timedelta(days=1))
    step = iter(range(1, 100))

    def at() -> datetime.datetime:
        return t0 + datetime.timedelta(minutes=next(step))

    def run(version, status, units, ref):
        rec.confirm(version.number, at=at())
        rec.apply_result(ExecutionResult(version.number, status, _broker(units), at(), ref))

    run(rec.propose_execution(at=at()), ResultStatus.COMPLETE, 75, "e1")
    assert m.adjustments_made(rec, at()).value == 0
    run(rec.edit(_definition(150), at=at(), reason="add a lot"), ResultStatus.COMPLETE, 150, "e2")
    assert m.adjustments_made(rec, at()).value == 1
    run(rec.edit(_definition(225), at=at(), reason="add"), ResultStatus.REJECTED, 150, "e3")
    assert m.adjustments_made(rec, at()).value == 1
    run(rec.edit(_definition(225), at=at(), reason="retry by user"), ResultStatus.COMPLETE, 225, "e4")
    value = m.adjustments_made(rec, at())
    assert value.value == 2 and value.inputs["activated_versions"] == (1, 2, 4)
    with pytest.raises(ValueError, match="StrategyRecord"):
        m.adjustments_made([1, 2, 4], at())


# --- One engine (ADR-008) ---------------------------------------------------------------------------------------
def test_calculators_carry_no_formula_of_their_own(golden, monkeypatch):
    """AC-1 / ADR-008: patching the engine's one P&L convention changes rows 8, 9, 10 and 11 together; patching the
    engine's IV solver changes rows 4 and 26; patching the engine's net premium changes row 14."""
    monkeypatch.setattr(engine_legs, "position_pnl", lambda leg, value: D("-1"))
    assert m.unrealised_pnl(golden).value == D("-4")  # 4 legs x -1
    assert m.pnl_at_level(golden, D("23000")).value == D("-4")
    assert m.booked_pnl([closed(IRON_CONDOR[3], "39.50", "f1")], VALUATION).value.total == D("-1")
    # open 3 legs: -3 at every point, slope 0; minus 1 booked -> -4
    assert m.remaining_profit(strategy_input(IRON_CONDOR[:3]), [closed(IRON_CONDOR[3], "39.50", "f1")]).value == D("-4")
    monkeypatch.undo()

    monkeypatch.setattr(bs, "implied_volatility", lambda *a, **k: D("0.2"))
    assert m.implied_volatility(golden, 2).value == D("0.2")
    assert m.option_delta(golden, 2).inputs["iv"] == D("0.2")
    assert m.option_delta(golden, 2).value != D("0.3327")
    monkeypatch.setattr(engine_strategy, "net_premium", lambda strategy, basis: D("7"))
    assert m.net_premium_now(golden).value == D("7")


def test_model_rows_need_an_ltp_and_values_are_immutable(golden):
    """AC-1 rows 4/26: an option leg without an LTP is refused (no IV to imply); a recorded input mapping cannot be
    changed after the fact; a MetricValue with a naive as_of is refused."""
    no_ltp = strategy_input([IRON_CONDOR[2][:4] + (None, None)])
    with pytest.raises(ValueError, match="no LTP"):
        m.option_delta(no_ltp, 0)
    with pytest.raises(ValueError, match="no LTP"):
        m.implied_volatility(no_ltp, 0)
    value = m.option_delta(golden, 2)
    with pytest.raises(TypeError):
        value.inputs["iv"] = D("0.5")
    with pytest.raises(ValueError, match="timezone-aware"):
        m.MetricValue(4, D("0.3"), datetime.datetime(2026, 10, 17), {})
